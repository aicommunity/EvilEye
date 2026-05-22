from ..core.base_class import EvilEyeBase
from ..core.processor_source import ProcessorSource
from ..core.processor_frame import ProcessorFrame
from ..core.processor_step import ProcessorStep
from ..core.processor_base import ProcessorBase
from ..core.pipeline_processors import PipelineProcessors
from typing import Any, Tuple, List, Dict
import evileye.preprocessing  # Import to register PreprocessingPipeline
import evileye.attributes_detection  # Import to register RoiFeeder and AttributeClassifier
import evileye.object_multi_camera_tracker  # Import to register ObjectMultiCameraTracking


class PipelineSurveillance(PipelineProcessors):
    """
    Surveillance pipeline implementation.
    Contains all surveillance-specific functionality including processor initialization
    and parameter management for the specific sequence: sources -> preprocessors -> detectors -> trackers -> mc_trackers
    """

    def __init__(self):
        super().__init__()
        # Инициализация для избежания hasattr проверок
        self.detectors = []
        self.results_selection_mode = "sticky_non_empty"

    def init_impl(self, **kwargs):
        """Initialize surveillance pipeline with specific processor sequence"""

        # Get pipeline parameters
        pipeline_params = self._normalize_pipeline_params(self.params)

        # Initialize encoders first
        self._init_encoders(pipeline_params.get("trackers", []))

        # Initialize processors in surveillance-specific order
        self._init_sources(pipeline_params.get("sources", []), self._credentials)
        self._init_preprocessors(pipeline_params.get("preprocessors", []))
        detectors_params = pipeline_params.get("detectors", [])
        self._init_detectors(detectors_params)
        self._init_trackers(pipeline_params.get("trackers", []))
        self._init_mc_trackers(pipeline_params.get("mc_trackers", []))

        self._init_attributes_roi(pipeline_params.get("attributes_roi", []))
        self._init_attribute_classifier(pipeline_params.get("attributes_classifier", []))
        self.results_selection_mode = str(
            pipeline_params.get("results_selection_mode", self.results_selection_mode)
            or "sticky_non_empty"
        ).lower()

        # Выбираем "финальную" секцию результатов детерминированно по enable-флагам.
        # Это определяет, какие (data, frame) считаются "прошедшими обработку" для визуализации/стриминга.
        def _enabled(section: str) -> bool:
            try:
                params_list = pipeline_params.get(section, []) or []
                if not isinstance(params_list, list) or not params_list:
                    return False
                for p in params_list:
                    if isinstance(p, dict) and bool(p.get("enable", True)):
                        return True
                return False
            except Exception:
                return False

        if _enabled("mc_trackers"):
            self._final_results_name = "mc_trackers"
        elif _enabled("trackers"):
            self._final_results_name = "trackers"
        elif _enabled("detectors"):
            self._final_results_name = "detectors"
        else:
            self._final_results_name = "sources"

        return True

    def _normalize_pipeline_params(self, params: Dict) -> Dict:
        """Normalize ipc/execution modes for all processor sections."""
        normalized = dict(params or {})
        ipc_mode = str(normalized.get("ipc_mode", "standard") or "standard")
        normalized["ipc_mode"] = ipc_mode
        sections = (
            "sources",
            "preprocessors",
            "detectors",
            "trackers",
            "mc_trackers",
            "attributes_roi",
            "attributes_classifier",
        )
        for section in sections:
            section_items = normalized.get(section, []) or []
            if not isinstance(section_items, list):
                continue
            updated = []
            for item in section_items:
                if not isinstance(item, dict):
                    updated.append(item)
                    continue
                item_copy = dict(item)
                item_copy.setdefault("ipc_mode", ipc_mode)
                updated.append(item_copy)
            normalized[section] = updated
        self.params = normalized
        return normalized

    # Surveillance-specific processor initialization methods
    def _init_sources(self, params: List[Dict], credentials: Dict | None):
        """Initialize source processors for surveillance"""
        if not params:
            return

        num_sources = len(params)
        # Get class_name from config, default to VideoCaptureOpencv
        class_name = params[0].get("type", "VideoCaptureOpencv") if params else "VideoCaptureOpencv"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in sources configuration. Using default: {class_name}")

        sources_proc = ProcessorSource(processor_name="sources", class_name=class_name, num_processors=num_sources,
                                       order=0)

        # Merge credentials if available
        if credentials and isinstance(credentials, dict):
            creds_sources = credentials.get("sources", {})
            for i in range(num_sources):
                src_params = params[i]
                camera_creds = creds_sources.get(src_params.get("camera"), None)
                if camera_creds and (not src_params.get("username") or not src_params.get("password")):
                    src_params["username"] = camera_creds.get("username", src_params.get("username"))
                    src_params["password"] = camera_creds.get("password", src_params.get("password"))

        sources_proc.set_params(params)
        init_result = sources_proc.init()
        # Don't raise exception on init failure - let reconnect logic handle it
        # Sources will be initialized later by reconnect loop if init fails
        if not init_result:
            self.logger.warning(f"Initial sources processor init failed: {sources_proc}; reconnect logic will retry")
        self._add_processor(sources_proc)
        self.sources_proc = sources_proc

    def _init_preprocessors(self, params: List[Dict]):
        """Initialize preprocessor processors for surveillance"""
        if not params:
            return

        num_preps = len(params)
        # Get class_name from config, default to PreprocessingPipeline
        class_name = params[0].get("type", "PreprocessingPipeline") if params else "PreprocessingPipeline"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in preprocessors configuration. Using default: {class_name}")

        preprocessors_proc = ProcessorFrame(processor_name="preprocessors", class_name=class_name,
                                            num_processors=num_preps, order=1)
        preprocessors_proc.set_params(params)
        preprocessors_proc.init()
        self._add_processor(preprocessors_proc)

    def _init_detectors(self, params: List[Dict]):
        """Initialize detector processors for surveillance"""
        if not params:
            return

        num_det = len(params)
        # Get class_name from config, default to ObjectDetectorYolo
        class_name = params[0].get("type", "ObjectDetectorYolo") if params else "ObjectDetectorYolo"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in detectors configuration. Using default: {class_name}")

        detectors_proc = ProcessorStep(processor_name="detectors", class_name=class_name, num_processors=num_det,
                                       order=2)
        detectors_proc.set_params(params)
        detectors_proc.init()
        self._add_processor(detectors_proc)
        # Сохраняем прямые ссылки на инициализированные детекторы для внешнего доступа
        try:
            self.detectors = list(getattr(detectors_proc, 'processors', []))
            self.logger.info(f"PipelineSurveillance: initialized {len(self.detectors)} detectors")
        except Exception:
            self.detectors = []

    def _init_trackers(self, params: List[Dict]):
        """Initialize tracker processors for surveillance"""
        if not params:
            return

        num_trackers = len(params)
        # Get class_name from config, default to ObjectTrackingBotsort
        class_name = params[0].get("type", "ObjectTrackingBotsort") if params else "ObjectTrackingBotsort"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in trackers configuration. Using default: {class_name}")

        trackers_proc = ProcessorStep(processor_name="trackers", class_name=class_name, num_processors=num_trackers,
                                      order=3)
        trackers_proc.set_params(params)
        trackers_proc.init(encoders=self.encoders)
        self._add_processor(trackers_proc)

    def _init_mc_trackers(self, params: List[Dict]):
        """Initialize multi-camera tracker processors for surveillance"""
        if not params:
            return

        num_trackers = len(params)
        # Get class_name from config, default to ObjectMultiCameraTracking
        class_name = params[0].get("type", "ObjectMultiCameraTracking") if params else "ObjectMultiCameraTracking"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in mc_trackers configuration. Using default: {class_name}")

        mc_trackers_proc = ProcessorStep(processor_name="mc_trackers", class_name=class_name,
                                         num_processors=num_trackers, order=4)
        mc_trackers_proc.set_params(params)
        mc_trackers_proc.init(encoders=self.encoders)
        self._add_processor(mc_trackers_proc)

    def _init_attributes_roi(self, params: List[Dict]):
        """Initialize ROI feeder for attributes if configured"""
        if not params:
            return
        num = len(params)
        # Get class_name from config, default to RoiFeeder
        class_name = params[0].get("type", "RoiFeeder") if params else "RoiFeeder"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in attributes_roi configuration. Using default: {class_name}")

        roi_proc = ProcessorStep(processor_name="attributes_roi", class_name=class_name, num_processors=num, order=4)
        roi_proc.set_params(params)
        roi_proc.init()
        self._add_processor(roi_proc)

    def _init_attribute_classifier(self, params: List[Dict]):
        """Initialize AttributeClassifier as ProcessorFrame if configured"""
        if not params:
            return
        num = len(params)
        # Get class_name from config, default to AttributeClassifier
        class_name = params[0].get("type", "AttributeClassifier") if params else "AttributeClassifier"
        if not any(param.get("type") for param in params):
            self.logger.warning(
                f"Warning: 'type' parameter not found in attributes_classifier configuration. Using default: {class_name}")

        cls_proc = ProcessorStep(processor_name="attributes_classifier", class_name=class_name, num_processors=num,
                                 order=5)
        cls_proc.set_params(params)
        cls_proc.init()
        self._add_processor(cls_proc)

    def _init_encoders(self, tracker_params_list: List[Dict]):
        """Initialize encoders for tracking in surveillance pipeline"""
        self.encoders = {}
        if self._trackers_use_process_mode(tracker_params_list):
            self.logger.info(
                "Skipping parent-process OnnxEncoder init "
                "(trackers use process mode; encoder loads in worker)"
            )
            return
        for tracker_params in tracker_params_list:
            path = tracker_params.get("tracker_onnx", "models/osnet_ain_x1_0_M.onnx")
            if path not in self.encoders:
                # Lazy import to avoid circular imports during module load time
                try:
                    from ..object_tracker.trackers.onnx_encoder import OnnxEncoder
                    import os
                    self.encoders[path] = OnnxEncoder(path)
                except ImportError:
                    self.logger.warning(
                        "Failed to import OnnxEncoder for '%s'; ReID encoder disabled",
                        path,
                    )
                except Exception as e:
                    self.logger.warning(
                        "Failed to initialize OnnxEncoder for '%s': %s. ReID encoder disabled",
                        path,
                        e,
                    )

    @staticmethod
    def _trackers_use_process_mode(tracker_params_list: List[Dict]) -> bool:
        for tracker_params in tracker_params_list or []:
            if not isinstance(tracker_params, dict):
                continue
            if str(tracker_params.get("execution_mode", "process")).lower() == "process":
                return True
        return False

    def generate_default_structure(self, num_sources: int):
        """Generate default structure for pipeline"""
        params = {
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://url",
                    "width": 1920,
                    "height": 1080,
                    "fps": 30,
                    "source_ids": [i],
                    "source_names": [f"Cam{i + 1}"]
                }
                for i in range(num_sources)
            ],
            "detectors": [
                {
                    "source_ids": [i]
                }
                for i in range(num_sources)
            ],
            "trackers": [
                {
                    "source_ids": [i]
                }
                for i in range(num_sources)
            ],
            "mc_trackers": [
                {
                    "source_ids": list(range(num_sources)),
                    "enable": False
                }
            ]
        }

        self.set_params(**params)
        self.init()

    def _enabled_pipeline_section(self, section: str) -> bool:
        try:
            params_list = self.get_processor_params(section) or []
            if not isinstance(params_list, list) or not params_list:
                return False
            for p in params_list:
                if isinstance(p, dict) and bool(p.get("enable", True)):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def _normalize_results_section(section_data: Any) -> list[Any]:
        if isinstance(section_data, (list, tuple)):
            return list(section_data)
        if section_data is not None:
            return [section_data]
        return []

    @staticmethod
    def _section_items_have_tracks(section_data: Any) -> bool:
        if not isinstance(section_data, (list, tuple)):
            return False
        for item in section_data:
            if not (isinstance(item, (list, tuple)) and len(item) >= 2):
                continue
            data = item[0]
            tracks = getattr(data, "tracks", None)
            if tracks:
                return True
        return False

    def _sticky_non_empty_section(self, section_name: str) -> list[Any]:
        last_non_empty = None
        for result in self.get_results_iterator():
            if not isinstance(result, dict):
                continue
            section = result.get(section_name, [])
            if not isinstance(section, (list, tuple)) or not section:
                continue
            if section_name == "mc_trackers":
                if self._section_items_have_tracks(section):
                    last_non_empty = section
            else:
                last_non_empty = section
        return self._normalize_results_section(last_non_empty)

    def _resolve_final_section_results(self, *, sticky: bool) -> list[Any]:
        section = self.get_final_results_name()
        if not section:
            return []
        if not sticky:
            latest = self.peek_latest_result()
            if not isinstance(latest, dict):
                return []
            return self._normalize_results_section(latest.get(section, []))
        return self._sticky_non_empty_section(section)

    def _resolve_section_chain(self, sections: tuple[str, ...], *, sticky: bool) -> list[Any]:
        for section_name in sections:
            if section_name == self.get_final_results_name():
                data = self._resolve_final_section_results(sticky=sticky)
            elif not sticky:
                latest = self.peek_latest_result()
                if not isinstance(latest, dict):
                    data = []
                else:
                    data = self._normalize_results_section(latest.get(section_name, []))
            else:
                data = self._sticky_non_empty_section(section_name)
            if data:
                return data
        return []

    def get_latest_visualization_frames(self) -> list[Any]:
        """
        Return frames for visualization/streaming.

        Prefer mc_trackers (same frame_id as objects when both are sticky), then raw
        sources so video keeps flowing under MP backpressure. No cross-stage fallback
        to trackers.
        """
        sticky = self.results_selection_mode != "strict_latest"
        sections: list[str] = []
        if self._enabled_pipeline_section("mc_trackers"):
            sections.append("mc_trackers")
        sections.append("sources")
        return self._resolve_section_chain(tuple(sections), sticky=sticky)

    def get_latest_objects_results(self) -> list[Any]:
        """Return tracking results for GUI from final section only (usually mc_trackers)."""
        sticky = self.results_selection_mode != "strict_latest"
        return self._resolve_final_section_results(sticky=sticky)

    # === ROI Editor integration helpers ===
    def get_detectors(self):
        """Возвращает список инстансов детекторов, если они инициализированы."""
        try:
            if isinstance(self.detectors, list) and self.detectors:
                return self.detectors
            # Попробуем получить из внутренних процессоров
            if self.processors:
                for proc in self.processors:
                    try:
                        if getattr(proc, 'processor_name', '') == 'detectors' and hasattr(proc, 'processors'):
                            return proc.processors
                    except Exception:
                        continue
        except Exception:
            pass
        return []

    def get_detector_by_index(self, idx: int):
        try:
            dets = self.get_detectors()
            if 0 <= idx < len(dets):
                return dets[idx]
        except Exception:
            pass
        return None

    def estimate_mp_pending_depth(self) -> tuple[int, int]:
        """Sum MP pending queue depth and drop counters (detectors + trackers)."""
        pending = 0
        dropped = 0
        try:
            from ..object_detector.detection_thread_yolo_mp import DetectionThreadYoloMp

            for det in self.get_detectors() or []:
                for th in getattr(det, "detection_threads", []) or []:
                    if isinstance(th, DetectionThreadYoloMp):
                        with th._mp_pending_lock:
                            pending += len(th._mp_pending)
                        dropped += int(getattr(th, "_diag_mp_put_dropped", 0))
        except Exception:
            pass
        try:
            for proc in self.processors or []:
                if getattr(proc, "processor_name", "") != "trackers":
                    continue
                from contextlib import nullcontext

                for trk in getattr(proc, "processors", []) or []:
                    lock = getattr(trk, "_mp_pending_lock", None)
                    with lock if lock is not None else nullcontext():
                        pending += len(getattr(trk, "_mp_pending", []) or [])
                    dropped += int(getattr(trk, "_diag_mp_put_dropped", 0))
        except Exception:
            pass
        return pending, dropped
