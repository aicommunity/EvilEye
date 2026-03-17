from __future__ import annotations

from abc import abstractmethod
from queue import Queue
import threading
import time
from time import sleep
from typing import Optional
import logging

from ..capture.video_capture_base import CaptureImage
from .object_detection_base import DetectionResult, DetectionResultList
from .constants import DEFAULT_THREAD_QUEUE_SIZE, PROCESSING_SLEEP_INTERVAL


class DetectionThreadBase:
    """
    Base class for detection threads.
    Handles image processing, prediction, and result extraction.
    """

    def __init__(
        self,
        stride: int,
        classes: list,
        source_ids: list,
        roi: list,
        inf_params: dict,
        queue_out: Queue,
        logger_name: Optional[str] = None,
        parent_logger: Optional[logging.Logger] = None,
    ):
        super().__init__()
        base_name = "evileye.detection_thread"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)

        self.prev_time = 0  # For time-based stride parameter; time tracking
        self.stride = stride  # Frame stride parameter
        self.stride_cnt = self.stride  # Counter for frames to skip
        self.classes = classes
        self.roi = roi  # [[]]
        self.inf_params = inf_params
        self.run_flag = False
        self.queue_in = Queue(maxsize=DEFAULT_THREAD_QUEUE_SIZE)
        self.queue_out = queue_out
        self.source_ids = source_ids
        self.processing_thread = threading.Thread(target=self._process_impl)
        self.roi_coords_per_camera = {
            source_id: roi_coords for source_id, roi_coords in zip(self.source_ids, self.roi)
        }
        self.model_class_mapping: Optional[dict] = None

    def start(self) -> None:
        """Start the detection thread."""
        self.run_flag = True
        self.processing_thread.start()

    def stop(self) -> None:
        """Stop the detection thread."""
        self.run_flag = False
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info("Detection thread stopped")

    def put(self, image: CaptureImage, force: bool = False) -> tuple[bool, list]:
        """
        Put image into thread queue for processing.
        Returns (success, dropped_id) tuple.
        """
        dropped_id = []
        if not self.run_flag:
            self.logger.warning(
                f"Detection thread not started. Put ignored for {image.source_id}:{image.frame_id}"
            )
            return False, dropped_id

        try:
            self.queue_in.put_nowait(image)
            return True, dropped_id
        except Exception:
            # Queue is full
            if force:
                try:
                    dropped_image = self.queue_in.get_nowait()
                    dropped_id.extend([dropped_image.source_id, dropped_image.frame_id])
                    self.queue_in.put_nowait(image)
                    return True, dropped_id
                except Exception:
                    dropped_id.extend([image.source_id, image.frame_id])
                    return False, dropped_id
            dropped_id.extend([image.source_id, image.frame_id])
            return False, dropped_id

    def get_model_class_mapping(self) -> Optional[dict]:
        """Get model class mapping dictionary."""
        return self.model_class_mapping

    def _update_model_class_mapping_from_model(self) -> None:
        """Update model_class_mapping from loaded model (implemented in subclasses)."""
        return None

    def _process_impl(self) -> None:
        """Main processing loop for detection thread."""
        while self.run_flag:
            self.init_detection_implementation()
            try:
                image = self.queue_in.get(timeout=PROCESSING_SLEEP_INTERVAL)
            except Exception:
                image = None

            if not image:
                sleep(PROCESSING_SLEEP_INTERVAL)
                continue

            if not self.roi[0]:
                split_image = [[image, [0, 0]]]
            else:
                coords = self.roi_coords_per_camera[image.source_id]
                from ..utils import utils

                split_image = utils.create_roi(image, coords)

            detection_result_list = self.process_stride(split_image)
            if detection_result_list is not None:
                try:
                    self.queue_out.put_nowait([detection_result_list, image])
                except Exception:
                    # Keep the newest results: drop oldest and push latest.
                    # This prevents long-lived backlog when downstream is slower.
                    try:
                        _ = self.queue_out.get_nowait()
                        self.queue_out.put_nowait([detection_result_list, image])
                    except Exception:
                        self.logger.warning(
                            f"Output queue full, dropping detection result for {image.source_id}:{image.frame_id}"
                        )

    def process_stride(self, split_image: list) -> Optional[DetectionResultList]:
        """
        Process images with stride and return detection results.
        """
        images = [img[0].image for img in split_image]
        predict_results = self._run_prediction(images, len(split_image))
        # Important contract: we must emit a result for each processed input frame (even if empty),
        # otherwise downstream visualization buffering can stall when there are no detections.
        if not predict_results:
            detection_result_list = DetectionResultList()
            detection_result_list.source_id = split_image[0][0].source_id
            detection_result_list.time_stamp = time.time()
            detection_result_list.frame_id = split_image[0][0].frame_id
            return detection_result_list

        bboxes_coords, confidences, class_ids = self._extract_bboxes_from_results(
            predict_results, split_image
        )
        if not bboxes_coords:
            detection_result_list = DetectionResultList()
            detection_result_list.source_id = split_image[0][0].source_id
            detection_result_list.time_stamp = time.time()
            detection_result_list.frame_id = split_image[0][0].frame_id
            return detection_result_list

        bboxes_coords, confidences, class_ids = self._post_process_detections(
            bboxes_coords, confidences, class_ids
        )
        if not bboxes_coords:
            detection_result_list = DetectionResultList()
            detection_result_list.source_id = split_image[0][0].source_id
            detection_result_list.time_stamp = time.time()
            detection_result_list.frame_id = split_image[0][0].frame_id
            return detection_result_list

        return self._create_detection_result_list(
            split_image, bboxes_coords, confidences, class_ids
        )

    def _run_prediction(self, images: list, expected_count: int) -> list:
        """Run model prediction on images."""
        try:
            predict_results = self.predict(images)
        except Exception as e:
            self.logger.error(f"Error during prediction: {e}")
            self.logger.debug("Prediction error details", exc_info=True)
            return [None] * expected_count

        if predict_results is None:
            return [None] * expected_count
        if not isinstance(predict_results, list):
            return [predict_results]
        return predict_results

    def _extract_bboxes_from_results(
        self, predict_results: list, split_image: list
    ) -> tuple[list, list, list]:
        """Extract bounding boxes from prediction results."""
        bboxes_coords = []
        confidences = []
        class_ids = []

        for i in range(len(split_image)):
            try:
                result = predict_results[i] if i < len(predict_results) else None
                roi_bboxes, roi_confs, roi_ids = self.get_bboxes(result, split_image[i])
                confidences.extend(roi_confs)
                class_ids.extend(roi_ids)
                bboxes_coords.extend(roi_bboxes)
            except Exception as e:
                self.logger.warning(f"Error processing bboxes for split image {i}: {e}")
                self.logger.debug("Bbox processing error", exc_info=True)

        return bboxes_coords, confidences, class_ids

    def _post_process_detections(
        self, bboxes_coords: list, confidences: list, class_ids: list
    ) -> tuple[list, list, list]:
        """Post-process detections: merge ROI boxes, apply NMS, filter by classes."""
        from ..utils import utils

        bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(
            self.roi[0], bboxes_coords, confidences, class_ids
        )
        bboxes_coords, confidences, class_ids = utils.non_max_sup(
            bboxes_coords, confidences, class_ids
        )
        bboxes_coords, confidences, class_ids = self._filter_detections(
            bboxes_coords, confidences, class_ids
        )
        return bboxes_coords, confidences, class_ids

    def _create_detection_result_list(
        self, split_image: list, bboxes_coords: list, confidences: list, class_ids: list
    ) -> DetectionResultList:
        """Create DetectionResultList from processed detections."""
        detection_result_list = DetectionResultList()
        detection_result_list.source_id = split_image[0][0].source_id
        detection_result_list.time_stamp = time.time()
        detection_result_list.frame_id = split_image[0][0].frame_id

        for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            detection_result = DetectionResult()
            detection_result.bounding_box = [int(x) for x in bbox]
            detection_result.class_id = int(class_id)
            detection_result.confidence = conf
            detection_result_list.detections.append(detection_result)

        return detection_result_list

    def _get_classes_arg_for_model(self) -> Optional[list[int]]:
        """
        Return list of class IDs to pass into model or None if not applicable.
        Avoid passing string names into Ultralytics models.
        """
        try:
            if isinstance(self.classes, list) and self.classes and all(
                isinstance(c, int) for c in self.classes
            ):
                return self.classes
            return None
        except Exception:
            return None

    def _filter_detections(
        self, bboxes_coords: list, confidences: list, class_ids: list
    ) -> tuple[list, list, list]:
        """
        Apply class filtering by IDs or names using model_class_mapping.
        """
        try:
            if not isinstance(self.classes, list) or not self.classes:
                return bboxes_coords, confidences, class_ids

            if all(isinstance(c, int) for c in self.classes):
                desired_ids = set(self.classes)
            elif (
                all(isinstance(c, str) for c in self.classes)
                and isinstance(self.model_class_mapping, dict)
                and self.model_class_mapping
            ):
                desired_ids = {
                    cid for name, cid in self.model_class_mapping.items() if name in self.classes
                }
                if not desired_ids:
                    return [], [], []
            else:
                return bboxes_coords, confidences, class_ids

            filtered_bboxes, filtered_confs, filtered_ids = [], [], []
            for b, c, i in zip(bboxes_coords, confidences, class_ids):
                cid = int(i)
                if cid in desired_ids:
                    filtered_bboxes.append(b)
                    filtered_confs.append(c)
                    filtered_ids.append(cid)
            return filtered_bboxes, filtered_confs, filtered_ids
        except Exception:
            return bboxes_coords, confidences, class_ids

    @abstractmethod
    def init_detection_implementation(self) -> None:
        """Initialize detection model implementation."""
        raise NotImplementedError

    @abstractmethod
    def predict(self, images: list) -> list:
        """Run prediction on images."""
        raise NotImplementedError

    @abstractmethod
    def get_bboxes(self, result, roi: list) -> tuple[list, list, list]:
        """Extract bboxes from prediction result."""
        raise NotImplementedError
