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

    def init_impl(self, **kwargs):
        """Initialize surveillance pipeline with specific processor sequence"""
        
        # Get pipeline parameters
        pipeline_params = self.params
        
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

        # Set final results name dynamically based on mc_trackers status
        mc_trackers_enabled = any(tracker.get("enable", True) for tracker in pipeline_params.get("mc_trackers", []))

        return True

    # Surveillance-specific processor initialization methods
    def _init_sources(self, params: List[Dict], credentials: Dict|None):
        """Initialize source processors for surveillance"""
        if not params:
            return
            
        num_sources = len(params)
        # Get class_name from config, default to VideoCaptureOpencv
        class_name = params[0].get("type", "VideoCaptureOpencv") if params else "VideoCaptureOpencv"
        if not any(param.get("type") for param in params):
            self.logger.warning(f"Warning: 'type' parameter not found in sources configuration. Using default: {class_name}")
        
        sources_proc = ProcessorSource(processor_name="sources", class_name=class_name, num_processors=num_sources, order=0)

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
        if not init_result:
            raise Exception(f"Failed to initialize sources processor: {sources_proc}")
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
            self.logger.warning(f"Warning: 'type' parameter not found in preprocessors configuration. Using default: {class_name}")
        
        preprocessors_proc = ProcessorFrame(processor_name="preprocessors", class_name=class_name, num_processors=num_preps, order=1)
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
            self.logger.warning(f"Warning: 'type' parameter not found in detectors configuration. Using default: {class_name}")
        
        detectors_proc = ProcessorStep(processor_name="detectors", class_name=class_name, num_processors=num_det, order=2)
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
            self.logger.warning(f"Warning: 'type' parameter not found in trackers configuration. Using default: {class_name}")
        
        trackers_proc = ProcessorStep(processor_name="trackers", class_name=class_name, num_processors=num_trackers, order=3)
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
            self.logger.warning(f"Warning: 'type' parameter not found in mc_trackers configuration. Using default: {class_name}")
        
        mc_trackers_proc = ProcessorStep(processor_name="mc_trackers", class_name=class_name, num_processors=num_trackers, order=4)
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
            self.logger.warning(f"Warning: 'type' parameter not found in attributes_roi configuration. Using default: {class_name}")
        
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
            self.logger.warning(f"Warning: 'type' parameter not found in attributes_classifier configuration. Using default: {class_name}")
        
        cls_proc = ProcessorStep(processor_name="attributes_classifier", class_name=class_name, num_processors=num, order=5)
        cls_proc.set_params(params)
        cls_proc.init()
        self._add_processor(cls_proc)

    def _init_encoders(self, tracker_params_list: List[Dict]):
        """Initialize encoders for tracking in surveillance pipeline"""
        self.encoders = {}
        for tracker_params in tracker_params_list:
            path = tracker_params.get("tracker_onnx", "models/osnet_ain_x1_0_M.onnx")
            if path not in self.encoders:
                # Lazy import to avoid circular imports during module load time
                try:
                    from ..object_tracker.trackers.onnx_encoder import OnnxEncoder
                    import os
                    self.encoders[path] = OnnxEncoder(path)
                except ImportError:
                    # Continue without encoder
                    pass
                except Exception:
                    # Continue without encoder
                    pass

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
                    "source_names": [f"Cam{i+1}"]
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

    # === ROI Editor integration helpers ===
    def get_detectors(self):
        """Возвращает список инстансов детекторов, если они инициализированы."""
        try:
            if hasattr(self, 'detectors') and isinstance(self.detectors, list):
                return self.detectors
            # Попробуем получить из внутренних процессоров
            if hasattr(self, '_processors'):
                for proc in self._processors:
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