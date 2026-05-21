from ..core.mp_worker import MpWorker
from ..core.tracking_dto import ensure_tracking_result_list


class MpWorkerRoiFeeder(MpWorker):
    """Multiprocessing worker for ROI extraction

    Receives (tracking_data, frame) tuples, extracts ROI crops from
    tracked object bounding boxes, and attaches roi_data to the
    tracking_data before forwarding
    """

    def __init__(self, input_queue, output_queue, log_queue=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue)
        self.padding = 0.0
        self.every_n_frames = 1
        self._frame_counters = {}

    def set_params(self, params: dict):
        self.padding = float(params.get('padding', 0.0))
        self.every_n_frames = int(params.get('every_n_frames', 1))

    def init_worker(self):
        pass

    def worker_impl(self, data):
        tracking_data, frame = data
        tracking_data = ensure_tracking_result_list(tracking_data)
        sid = frame.source_id
        self._frame_counters[sid] = self._frame_counters.get(sid, 0) + 1

        if self._frame_counters[sid] % self.every_n_frames == 0:
            self._extract_rois(tracking_data, frame)

        return data

    def _extract_rois(self, tracking_data, image):
        roi_data = []
        for track in tracking_data.tracks:
            roi_bbox = self._extract_roi_bbox(image.image, track.bounding_box)
            if roi_bbox is not None:
                roi_data.append({
                    'track_id': track.track_id,
                    'roi_bbox': roi_bbox,
                    'class_id': track.class_id,
                })
        if roi_data:
            tracking_data.roi_data = roi_data

    def _extract_roi_bbox(self, image, bbox):
        try:
            x1, y1, x2, y2 = bbox
            h, w = image.shape[:2]
            pad_x = int((x2 - x1) * self.padding)
            pad_y = int((y2 - y1) * self.padding)
            x1_pad = max(0, int(x1 - pad_x))
            y1_pad = max(0, int(y1 - pad_y))
            x2_pad = min(w, int(x2 + pad_x))
            y2_pad = min(h, int(y2 + pad_y))
            if x2_pad <= x1_pad or y2_pad <= y1_pad:
                return None
            return [x1_pad, y1_pad, x2_pad, y2_pad]
        except Exception:
            return None


class MpWorkerAttributeClassifier(MpWorker):
    """Multiprocessing worker for attribute classification

    Loads a YOLO model inside the child process and runs inference
    on ROI crops attached by the RoiFeeder stage
    """

    def __init__(self, input_queue, output_queue, log_queue=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue)
        self.model_path = "models/yolo11n.pt"
        self.attrs = []
        self.conf_threshold = 0.5
        self.inference_size = 224
        self.attr_class_mapping = {}
        self.yolo_model = None

    def set_params(self, params: dict):
        self.model_path = params.get('model', self.model_path)
        self.attrs = params.get('attrs', [])
        self.conf_threshold = params.get('conf_threshold', 0.5)
        self.inference_size = params.get('inference_size', 224)
        class_mapping = params.get('class_mapping', {})
        if not class_mapping:
            for i, attr_name in enumerate(self.attrs):
                self.attr_class_mapping[i] = attr_name
        else:
            for attr_name, class_id in class_mapping.items():
                if attr_name in self.attrs:
                    self.attr_class_mapping[class_id] = attr_name

    def init_worker(self):
        from ultralytics import YOLO
        from evileye.object_detector.ultralytics_postprocess import apply_ultralytics_optimizations

        self.yolo_model = YOLO(self.model_path)
        apply_ultralytics_optimizations(self.yolo_model, half=False, logger=self.logger)

    def worker_impl(self, data):
        tracking_data, frame = data
        tracking_data = ensure_tracking_result_list(tracking_data)
        if self.yolo_model is None:
            return data

        if hasattr(tracking_data, 'roi_data') and tracking_data.roi_data:
            for roi_info in tracking_data.roi_data:
                track_id = roi_info.get('track_id')
                roi_bbox = roi_info.get('roi_bbox')
                roi_image = self._crop_roi(frame.image, roi_bbox) if roi_bbox is not None else None
                if roi_image is not None and track_id is not None:
                    attr_results = self._classify_roi(roi_image)
                    if not hasattr(tracking_data, 'attr_results'):
                        tracking_data.attr_results = {}
                    tracking_data.attr_results[track_id] = attr_results

        return (tracking_data, frame)

    def _classify_roi(self, roi_image):
        try:
            results = self.yolo_model.predict(
                source=roi_image,
                classes=list(self.attr_class_mapping.keys()),
                verbose=False,
                conf=self.conf_threshold,
                imgsz=self.inference_size,
            )
            if not results or len(results) == 0:
                return {}
            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                return {n: {'detected_now': False, 'confidence': 0.0} for n in self.attrs}

            attr_results = {n: {'detected_now': False, 'confidence': 0.0} for n in self.attrs}
            boxes = result.boxes.cpu().numpy()
            for box in boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                attr_name = self.attr_class_mapping.get(class_id)
                if attr_name and confidence >= self.conf_threshold:
                    attr_results[attr_name] = {
                        'detected_now': True,
                        'confidence': confidence,
                        'bbox': box.xyxy[0].tolist(),
                        'class_id': class_id,
                    }
            return attr_results
        except Exception:
            return {}

    def _crop_roi(self, image, bbox):
        try:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            roi = image[y1:y2, x1:x2]
            if roi is None or roi.size == 0:
                return None
            return roi
        except Exception:
            return None

    def cleanup(self):
        if self.yolo_model is not None:
            del self.yolo_model
            self.yolo_model = None
