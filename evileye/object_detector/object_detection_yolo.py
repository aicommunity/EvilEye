import os
from .object_detection_base import (
    EXEC_MODE_PROCESS,
    DetectionResultList,
    ModelBasedDetectorBase,
    ObjectDetectorBase,
)
from ..core.base_class import EvilEyeBase
from ..core.plugins import register_module
from ..core.mp_control import parse_mp_restart_policy


@register_module(
    "ObjectDetectorYolo",
    kind="processor_item",
    capabilities=(
        "accepts_frame_handle",
        "model_class_mapping",
        "parallel_items",
    ),
    execution_modes=("thread", "process"),
    default_execution_mode="process",
    legacy_ids=("ObjectDetectorYoloMp",),
)
class ObjectDetectorYolo(ModelBasedDetectorBase):
    """YOLO-based object detector."""

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    ResultType = DetectionResultList

    def _create_plugin_runtime(self):
        from .yolo_runtime import YoloRuntime

        return YoloRuntime(logger=self.logger)

    def create_state(self, config, context=None):
        config = dict(config or {})
        self.model_name = config.get("model", self._get_default_model_name())
        self.source_ids = [
            int(item) for item in (
                config.get("source_ids")
                if config.get("source_ids") is not None
                else getattr(context, "source_ids", ())
            )
        ]
        self.roi = config.get("roi", [[]]) or [[]]
        self.stride = max(1, int(config.get("vid_stride", 1)))
        worker_count = int(getattr(context, "worker_count", 1))
        if worker_count > 1 and self.stride > 1:
            raise ValueError(
                f"{type(self).__name__} requires vid_stride=1 when worker_count > 1"
            )
        self.enabled = bool(config.get("enabled", True))
        self._plugin_confidence = float(config.get("conf", 0.25))
        self._plugin_inference_size = int(
            config.get("inference_size", config.get("imgsz", 640))
        )
        self._plugin_device = config.get("device")
        self._plugin_classes = list(config.get("classes") or [])
        self._plugin_frame_transport = None
        self._plugin_class_mapping = dict(config.get("model_class_mapping") or {})
        self._plugin_class_filter: list[int] | None = None

        self._plugin_model_runtime = self._create_plugin_runtime()
        self._plugin_model_runtime.configure(
            self.model_name,
            [],
            {
                "conf": self._plugin_confidence,
                "imgsz": self._plugin_inference_size,
                "device": self._plugin_device,
                "show": bool(config.get("show", False)),
                "save": bool(config.get("save", False)),
                "half": bool(config.get("half", True)),
            },
        )
        if self.enabled:
            self._plugin_model_runtime.load()
            model = self._plugin_model_runtime.model
            if model is None:
                raise RuntimeError(
                    f"{type(self).__name__} failed to load model '{self.model_name}'"
                )
            discovered_mapping = self._plugin_model_mapping(model)
            self._plugin_class_mapping = (
                self._plugin_class_mapping or discovered_mapping
            )
            if self._plugin_classes:
                if all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in self._plugin_classes
                ):
                    self._plugin_class_filter = list(self._plugin_classes)
                elif all(isinstance(value, str) for value in self._plugin_classes):
                    missing = [
                        value for value in self._plugin_classes
                        if value not in self._plugin_class_mapping
                    ]
                    if missing:
                        raise ValueError(
                            f"{type(self).__name__} class names are absent from model "
                            f"mapping: {missing}"
                        )
                    self._plugin_class_filter = [
                        self._plugin_class_mapping[value]
                        for value in self._plugin_classes
                    ]
                else:
                    raise ValueError(
                        f"{type(self).__name__} classes must contain only names or only IDs"
                    )
            self._plugin_model_runtime.classes = (
                list(self._plugin_class_filter or [])
            )
        self.model_class_mapping = dict(self._plugin_class_mapping)
        return {"frame_counts": {}}

    def _plugin_model_mapping(self, model):
        names = getattr(model, "names", None)
        if isinstance(names, dict):
            return {str(name): int(class_id) for class_id, name in names.items()}
        if isinstance(names, (list, tuple)):
            return {str(name): class_id for class_id, name in enumerate(names)}
        return {}

    def get_model_class_mapping(self):
        mapping = getattr(self, "_plugin_class_mapping", None)
        if mapping:
            return dict(mapping)
        return super().get_model_class_mapping()

    def _plugin_frame_image(self, frame):
        image = getattr(frame, "image", None)
        if image is not None and getattr(image, "size", 0) > 0:
            return image
        handle = getattr(frame, "frame_handle", None)
        if handle is None:
            handle = getattr(frame, "frame_ref", None)
        if handle is None:
            raise RuntimeError(
                f"{type(self).__name__} frame has neither image nor shared-frame handle"
            )
        if self._plugin_frame_transport is None:
            from ..core.frame_transport import SharedFrameTransport

            self._plugin_frame_transport = SharedFrameTransport()
        image = self._plugin_frame_transport.get_frame_view(handle)
        if image is None or getattr(image, "size", 0) == 0:
            raise RuntimeError(
                f"{type(self).__name__} could not read shared frame {handle.shm_name}"
            )
        return image

    def _plugin_rois(self, frame, image):
        height, width = image.shape[:2]
        roi_groups = self.roi
        if not isinstance(roi_groups, list) or not roi_groups:
            return [(0, 0, width, height)]
        if self.source_ids and frame.source_id in self.source_ids:
            index = self.source_ids.index(frame.source_id)
        elif len(roi_groups) == 1:
            index = 0
        else:
            raise ValueError(
                f"{type(self).__name__} has no ROI configuration for source "
                f"{frame.source_id}"
            )
        source_rois = roi_groups[index] if index < len(roi_groups) else []
        if not source_rois:
            return [(0, 0, width, height)]
        rois = []
        for roi in source_rois:
            if len(roi) != 4:
                raise ValueError(
                    f"{type(self).__name__} ROI must be [x, y, width, height]: {roi!r}"
                )
            x, y, roi_width, roi_height = (int(value) for value in roi)
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(width, x + roi_width)
            y2 = min(height, y + roi_height)
            if x2 > x1 and y2 > y1:
                rois.append((x1, y1, x2 - x1, y2 - y1))
        return rois

    def _plugin_roi_conversion_options(self):
        return {}

    def _plugin_roi_detections(self, crops, rois):
        from .bbox_utils import roi_boxes_to_image_coords
        from ..utils import utils

        predictions = self._plugin_model_runtime.predict_raw(
            crops,
            classes=self._plugin_class_filter,
        )
        if predictions is None:
            predictions = []
        elif not isinstance(predictions, list):
            predictions = [predictions]
        boxes, confidences, class_ids = [], [], []
        for index, roi in enumerate(rois):
            prediction = predictions[index] if index < len(predictions) else None
            roi_boxes, roi_confidences, roi_class_ids = roi_boxes_to_image_coords(
                prediction, (roi[0], roi[1]), logger=self.logger,
                **self._plugin_roi_conversion_options(),
            )
            boxes.extend(roi_boxes)
            confidences.extend(roi_confidences)
            class_ids.extend(roi_class_ids)
        if boxes:
            boxes, confidences, class_ids = utils.non_max_sup(
                boxes, confidences, class_ids
            )
        return boxes, confidences, class_ids

    def process_item(self, item, state):
        import numpy as np

        from ..core.frame import Frame
        from .object_detection_base import DetectionResult, DetectionResultList

        if isinstance(item, Frame):
            frame = item
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            frame = item[1]
        else:
            raise TypeError(f"{type(self).__name__} expects Frame or (data, Frame)")
        if not isinstance(frame, Frame):
            raise TypeError(f"{type(self).__name__} input must contain a Frame")

        output = DetectionResultList()
        output.source_id = frame.source_id
        output.frame_id = frame.frame_id
        output.time_stamp = frame.time_stamp
        state = state if isinstance(state, dict) else {"frame_counts": {}}
        frame_counts = state.setdefault("frame_counts", {})
        frame_counts[frame.source_id] = frame_counts.get(frame.source_id, 0) + 1
        if self.enabled and (
            (frame_counts[frame.source_id] - 1) % self.stride == 0
        ):
            image = self._plugin_frame_image(frame)
            rois = self._plugin_rois(frame, image)
            if not rois:
                return output, frame
            crops = [
                np.ascontiguousarray(image[y:y + height, x:x + width])
                for x, y, width, height in rois
            ]
            boxes, confidences, class_ids = self._plugin_roi_detections(
                crops, rois
            )
            for bbox, confidence, class_id in zip(
                boxes, confidences, class_ids
            ):
                detection = DetectionResult()
                detection.bounding_box = [int(value) for value in bbox]
                detection.confidence = float(confidence)
                detection.class_id = int(class_id)
                output.detections.append(detection)
        return output, frame

    def close(self):
        runtime = getattr(self, "_plugin_model_runtime", None)
        if runtime is not None:
            runtime.release()
        self._plugin_frame_transport = None

    def _get_detection_thread_type(self) -> str:
        return "yolo"

    def _get_default_model_name(self) -> str:
        return "models/yolo11n.pt"

    def init_impl(self):
        if self.execution_mode != EXEC_MODE_PROCESS:
            return super().init_impl()

        # Process-mode YOLO still needs the detector dispatcher thread from
        # ObjectDetectorBase: it drains detector.queue_in and forwards frames
        # into the per-worker DetectionThreadYoloMp instances.
        ObjectDetectorBase.init_impl(self)

        inf_params = {
            "show": self.params.get('show', False),
            'conf': self.params.get('conf', 0.25),
            'save': self.params.get('save', False),
            "imgsz": self.params.get('inference_size', 640),
            "device": self.params.get('device', None),
        }
        restart_on_exit, no_restart_exit_codes = parse_mp_restart_policy(
            self.params,
            default_restart_on_exit=True,
        )
        self.detection_threads = []
        return self._init_process_mode(
            inf_params,
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
        )

    def _init_process_mode(self, inf_params, restart_on_exit: bool, no_restart_exit_codes: set[int]):
        """Initialize YOLO inference workers in child processes."""
        from .detection_thread_yolo_mp import DetectionThreadYoloMp

        model_path = self.model_name or self._get_default_model_name()
        if not os.path.isabs(model_path):
            model_path = os.path.join(os.getcwd(), model_path)

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYoloMp(
                model_path, self.stride, self.classes,
                self.source_ids, self.roi, inf_params,
                restart_on_exit,
                no_restart_exit_codes,
                self.queue_out,
                logger_name=f"det{i}",
                parent_logger=self.logger,
                on_cuda_oom_fatal=self._report_cuda_oom_disabled,
            )
            thread.start()
            self.detection_threads.append(thread)
        try:
            from evileye.core.mp_cuda_startup import get_mp_cuda_startup_health

            get_mp_cuda_startup_health().register_expected_workers(self.num_detection_threads)
        except Exception:
            pass
        self.logger.info(
            f"Detection initialized in PROCESS mode with "
            f"{self.num_detection_threads} worker(s)"
        )
        return True
