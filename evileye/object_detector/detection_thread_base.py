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
from .constants import DEFAULT_THREAD_QUEUE_SIZE, PROCESSING_SLEEP_INTERVAL, DEFAULT_BATCH_SIZE, DEFAULT_BATCH_TIMEOUT_MS


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
        
        # Batching parameters (optional)
        self.batch_size = inf_params.get('batch_size', None)
        self.batch_timeout_ms = inf_params.get('batch_timeout_ms', DEFAULT_BATCH_TIMEOUT_MS) if inf_params.get('batch_timeout_ms') is not None else DEFAULT_BATCH_TIMEOUT_MS

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
        import time
        
        # Инициализировать модель один раз в начале цикла
        self.init_detection_implementation()
        
        while self.run_flag:
            # Если батчинг включен, собираем батч кадров
            if self.batch_size and self.batch_size > 1:
                batch_frames = []
                batch_start_time = time.time()
                
                # Собрать батч кадров
                while len(batch_frames) < self.batch_size:
                    try:
                        timeout = (self.batch_timeout_ms / 1000.0) - (time.time() - batch_start_time)
                        if timeout <= 0:
                            break
                        image = self.queue_in.get(timeout=max(0.001, timeout))
                        if image:
                            batch_frames.append(image)
                    except Exception:
                        break
                
                if batch_frames:
                    # Обработать батч кадров
                    self._process_batch(batch_frames)
                else:
                    sleep(PROCESSING_SLEEP_INTERVAL)
            else:
                # Стандартная обработка - один кадр за раз
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
                
                # Проверка что split_image не пустой и содержит валидные изображения
                if not split_image:
                    self.logger.debug(f"Empty split_image for source {image.source_id}, frame {image.frame_id}, skipping")
                    continue
                
                # Проверка что все изображения валидны (не None и имеют ненулевые размеры)
                valid_split_image = []
                for roi_item in split_image:
                    roi_capture, roi_offset = roi_item
                    if roi_capture and roi_capture.image is not None:
                        img = roi_capture.image
                        # Проверка что изображение имеет валидные размеры
                        if len(img.shape) >= 2 and img.shape[0] > 0 and img.shape[1] > 0:
                            valid_split_image.append(roi_item)
                        else:
                            self.logger.debug(f"Invalid image shape {img.shape if img is not None else 'None'} for ROI, skipping")
                    else:
                        self.logger.debug(f"None image in ROI, skipping")
                
                if not valid_split_image:
                    self.logger.debug(f"No valid images in split_image for source {image.source_id}, frame {image.frame_id}, skipping")
                    continue
                
                detection_result_list = self.process_stride(valid_split_image)
                if detection_result_list:
                    try:
                        self.queue_out.put_nowait([detection_result_list, image])
                    except Exception:
                        self.logger.warning(
                            f"Output queue full, dropping detection result for {image.source_id}:{image.frame_id}"
                        )

    def _process_batch(self, batch_frames: list) -> None:
        """
        Обработать батч кадров с правильным маппированием результатов.
        
        Args:
            batch_frames: Список CaptureImage объектов для обработки
        """
        from ..utils import utils
        
        # Подготовить данные для батча: собрать все изображения и сохранить метаданные
        batch_images = []
        batch_metadata = []  # [(source_id, frame_id, roi_coords, original_image), ...]
        
        for image in batch_frames:
            if not self.roi[0]:
                split_image = [[image, [0, 0]]]
            else:
                coords = self.roi_coords_per_camera[image.source_id]
                split_image = utils.create_roi(image, coords)
            
            # Проверка что split_image не пустой
            if not split_image:
                continue
            
            # Собрать изображения из всех ROI для этого кадра
            for roi_item in split_image:
                roi_image, roi_offset = roi_item
                if roi_image and roi_image.image is not None:
                    img = roi_image.image
                    # Проверка что изображение имеет валидные размеры
                    if len(img.shape) >= 2 and img.shape[0] > 0 and img.shape[1] > 0:
                        batch_images.append(img)
                        batch_metadata.append({
                            'source_id': image.source_id,
                            'frame_id': image.frame_id,
                            'roi_offset': roi_offset,
                            'original_image': image,
                            'roi_item': roi_item
                        })
                    else:
                        self.logger.debug(f"Invalid image shape {img.shape} in batch ROI, skipping")
                else:
                    self.logger.debug(f"None image in batch ROI, skipping")
        
        if not batch_images:
            return
        
        # Выполнить инференс на батче
        import time
        inference_start_time = time.time()
        predict_results = self._run_prediction(batch_images, len(batch_images))
        inference_time_ms = (time.time() - inference_start_time) * 1000.0
        
        # Передать метрику времени инференса
        if hasattr(self.queue_out, '_parent_detector'):
            parent = getattr(self.queue_out, '_parent_detector', None)
            if parent and hasattr(parent, '_metrics'):
                parent._metrics['total_inference_time_ms'] += inference_time_ms
        
        if not predict_results:
            return
        
        # Сгруппировать результаты по исходным кадрам
        results_by_frame = {}
        metadata_idx = 0
        
        for i, result in enumerate(predict_results):
            if metadata_idx >= len(batch_metadata):
                break
                
            meta = batch_metadata[metadata_idx]
            frame_key = (meta['source_id'], meta['frame_id'])
            
            if frame_key not in results_by_frame:
                results_by_frame[frame_key] = {
                    'image': meta['original_image'],
                    'roi_results': []
                }
            
            # Извлечь bboxes из результата для этого ROI
            # roi_item это [roi_capture, [x, y]], get_bboxes ожидает такой же формат
            roi_bboxes, roi_confs, roi_ids = self.get_bboxes(result, meta['roi_item'])
            
            results_by_frame[frame_key]['roi_results'].append({
                'bboxes': roi_bboxes,
                'confidences': roi_confs,
                'class_ids': roi_ids,
                'roi_offset': meta['roi_offset']
            })
            
            metadata_idx += 1
        
        # Создать DetectionResultList для каждого кадра в батче
        for (source_id, frame_id), frame_data in results_by_frame.items():
            # Объединить результаты от всех ROI для этого кадра
            all_bboxes = []
            all_confidences = []
            all_class_ids = []
            
            for roi_result in frame_data['roi_results']:
                all_bboxes.extend(roi_result['bboxes'])
                all_confidences.extend(roi_result['confidences'])
                all_class_ids.extend(roi_result['class_ids'])
            
            if not all_bboxes:
                continue
            
            # Применить постобработку (merge_roi_boxes, NMS, фильтрация)
            bboxes_coords, confidences, class_ids = self._post_process_detections(
                all_bboxes, all_confidences, all_class_ids
            )
            
            if not bboxes_coords:
                continue
            
            # Создать DetectionResultList для этого кадра
            detection_result_list = self._create_detection_result_list_for_frame(
                frame_data['image'], bboxes_coords, confidences, class_ids
            )
            
            if detection_result_list:
                try:
                    self.queue_out.put_nowait([detection_result_list, frame_data['image']])
                except Exception:
                    self.logger.warning(
                        f"Output queue full, dropping detection result for {source_id}:{frame_id}"
                    )
    
    def _create_detection_result_list_for_frame(
        self, image, bboxes_coords: list, confidences: list, class_ids: list
    ) -> Optional[DetectionResultList]:
        """Создать DetectionResultList для кадра из объединенных результатов ROI"""
        detection_result_list = DetectionResultList()
        detection_result_list.source_id = image.source_id
        detection_result_list.time_stamp = image.time_stamp
        detection_result_list.frame_id = image.frame_id

        for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            detection_result = DetectionResult()
            detection_result.bounding_box = [int(x) for x in bbox]
            detection_result.class_id = int(class_id)
            detection_result.confidence = conf
            detection_result_list.detections.append(detection_result)

        return detection_result_list

    def process_stride(self, split_image: list) -> Optional[DetectionResultList]:
        """
        Process images with stride and return detection results.
        """
        import time
        inference_start_time = time.time()
        
        images = [img[0].image for img in split_image]
        predict_results = self._run_prediction(images, len(split_image))
        
        # Отслеживание времени инференса
        inference_time_ms = (time.time() - inference_start_time) * 1000.0
        if hasattr(self.queue_out, '_parent_detector'):
            # Передать метрику времени инференса в родительский детектор
            parent = getattr(self.queue_out, '_parent_detector', None)
            if parent and hasattr(parent, '_metrics'):
                parent._metrics['total_inference_time_ms'] += inference_time_ms
        
        if not predict_results:
            return None

        bboxes_coords, confidences, class_ids = self._extract_bboxes_from_results(
            predict_results, split_image
        )
        if not bboxes_coords:
            return None

        bboxes_coords, confidences, class_ids = self._post_process_detections(
            bboxes_coords, confidences, class_ids
        )
        if not bboxes_coords:
            return None

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
