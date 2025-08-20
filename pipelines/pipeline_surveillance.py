from core import EvilEyeBase, ProcessorSource, ProcessorFrame, ProcessorStep
from core.pipeline import Pipeline
from typing import Any


class PipelineSurveillance(Pipeline):
    def __init__(self):
        super().__init__()
        self.sources_proc: ProcessorSource | None = None
        self.preprocessors_proc: ProcessorFrame | None = None
        self.detectors_proc: ProcessorStep | None = None
        self.trackers_proc: ProcessorStep | None = None
        self.mc_trackers_proc: ProcessorStep | None = None

        self.encoders: dict[str, Any] = {}

        self._sources_params: list[dict] = []
        self._preprocessors_params: list[dict] = []
        self._detectors_params: list[dict] = []
        self._trackers_params: list[dict] = []
        self._mc_trackers_params: list[dict] = []
        self._credentials: dict = {}

    def default(self):
        self._sources_params = []
        self._preprocessors_params = []
        self._detectors_params = []
        self._trackers_params = []
        self._mc_trackers_params = []
        self._credentials = {}
        self.encoders = {}

    def init_impl(self, **kwargs):
        # Initialize components in the same order as in Controller
        self._init_encoders(self._trackers_params)
        self._init_sources(self._sources_params, self._credentials)
        self._init_preprocessors(self._preprocessors_params)
        self._init_detectors(self._detectors_params)
        self._init_trackers(self._trackers_params)
        self._init_mc_trackers(self._mc_trackers_params)
        return True

    def release_impl(self):
        if self.mc_trackers_proc:
            self.mc_trackers_proc.release()
        if self.trackers_proc:
            self.trackers_proc.release()
        if self.detectors_proc:
            self.detectors_proc.release()
        if self.preprocessors_proc:
            self.preprocessors_proc.release()
        if self.sources_proc:
            self.sources_proc.release()

    def reset_impl(self):
        # No-op: keep current simple behavior
        return None

    def set_params_impl(self):
        # Expecting keys: sources, preprocessors, detectors, trackers, mc_trackers, credentials
        self._sources_params = self.params.get("sources", []) or []
        self._preprocessors_params = self.params.get("preprocessors", []) or []
        self._detectors_params = self.params.get("detectors", []) or []
        self._trackers_params = self.params.get("trackers", []) or []
        self._mc_trackers_params = self.params.get("mc_trackers", []) or []
        #self._credentials = self.params.get("credentials", {}) or {}

    def get_params_impl(self):
        params = dict()
        params["sources"] = {}
        self.sources_proc.get_params(params["sources"])
        params["preprocessors"] = {}
        self.preprocessors_proc.get_params(params["preprocessors"])
        params["detectors"] = {}
        self.detectors_proc.get_params(params["detectors"])
        params["trackers"] = {}
        self.trackers_proc.get_params(params["trackers"])
        params["mc_trackers"] = {}
        self.mc_trackers_proc.get_params(params["mc_trackers"])
        return params

    # Public helpers
    def start(self):
        if self.sources_proc:
            self.sources_proc.start()
        if self.preprocessors_proc:
            self.preprocessors_proc.start()
        if self.detectors_proc:
            self.detectors_proc.start()
        if self.trackers_proc:
            self.trackers_proc.start()
        if self.mc_trackers_proc:
            self.mc_trackers_proc.start()

    def stop(self):
        if self.mc_trackers_proc:
            self.mc_trackers_proc.stop()
        if self.trackers_proc:
            self.trackers_proc.stop()
        if self.detectors_proc:
            self.detectors_proc.stop()
        if self.preprocessors_proc:
            self.preprocessors_proc.stop()
        if self.sources_proc:
            self.sources_proc.stop()

    def process(self):
        captured_frames = []
        preprocessing_frames = []
        detection_results = []
        tracking_results = []
        mc_tracking_results = []
        all_sources_finished = True

        if self.sources_proc:
            captured_frames, all_sources_finished = self.sources_proc.process()
            # kick sources to continue producing
            self.run_sources()

        if self.preprocessors_proc:
            preprocessing_frames = self.preprocessors_proc.process(captured_frames)

        if self.detectors_proc:
            detection_results = self.detectors_proc.process(preprocessing_frames)

        if self.trackers_proc:
            tracking_results = self.trackers_proc.process(detection_results)

        if self.mc_trackers_proc:
            mc_tracking_results = self.mc_trackers_proc.process(tracking_results)

        return (
            captured_frames,
            preprocessing_frames,
            detection_results,
            tracking_results,
            mc_tracking_results,
            all_sources_finished,
        )

    def run_sources(self):
        if self.sources_proc:
            self.sources_proc.run_sources()

    def calc_memory_consumption(self):
        total = 0
        if self.sources_proc:
            self.sources_proc.calc_memory_consumption()
            total += self.sources_proc.get_memory_usage()
        if self.preprocessors_proc:
            self.preprocessors_proc.calc_memory_consumption()
            total += self.preprocessors_proc.get_memory_usage()
        if self.detectors_proc:
            self.detectors_proc.calc_memory_consumption()
            total += self.detectors_proc.get_memory_usage()
        if self.trackers_proc:
            self.trackers_proc.calc_memory_consumption()
            total += self.trackers_proc.get_memory_usage()
        if self.mc_trackers_proc:
            self.mc_trackers_proc.calc_memory_consumption()
            total += self.mc_trackers_proc.get_memory_usage()
        self.memory_measure_results = total

    def get_dropped_ids(self):
        dropped = []
        if self.detectors_proc:
            dropped.extend(self.detectors_proc.get_dropped_ids())
        if self.trackers_proc:
            dropped.extend(self.trackers_proc.get_dropped_ids())
        return dropped

    # Expose sources processors for external subscriptions (events, etc.)
    def get_sources_processors(self):
        return self.sources_proc.get_processors() if self.sources_proc else []

    def insert_debug_info_by_id(self, debug_info: dict):
        """
        Insert debug information from all pipeline components into debug_info dict.
        Collects debug data from sources, preprocessors, detectors, trackers, and mc_trackers.
        
        Args:
            debug_info: Dictionary to store debug information
        """
        if self.sources_proc:
            self.sources_proc.insert_debug_info_by_id("sources", debug_info)
        if self.preprocessors_proc:
            self.preprocessors_proc.insert_debug_info_by_id("preprocessors", debug_info)
        if self.detectors_proc:
            self.detectors_proc.insert_debug_info_by_id("detectors", debug_info)
        if self.trackers_proc:
            self.trackers_proc.insert_debug_info_by_id("trackers", debug_info)
        if self.mc_trackers_proc:
            self.mc_trackers_proc.insert_debug_info_by_id("mc_trackers", debug_info)

    # Internal initialization copied from Controller
    def _init_sources(self, params: list[dict], credentials: dict):
        num_sources = len(params)
        self.sources_proc = ProcessorSource(class_name="VideoCapture", num_processors=num_sources, order=0)

        # Merge credentials if available
        if credentials and isinstance(credentials, dict):
            creds_sources = credentials.get("sources", {})
            for i in range(num_sources):
                src_params = params[i]
                camera_creds = creds_sources.get(src_params.get("camera"), None)
                if camera_creds and (not src_params.get("username") or not src_params.get("password")):
                    src_params["username"] = camera_creds.get("username", src_params.get("username"))
                    src_params["password"] = camera_creds.get("password", src_params.get("password"))

        self.sources_proc.set_params(params)
        self.sources_proc.init()

    def _init_preprocessors(self, params: list[dict]):
        num_preps = len(params)
        self.preprocessors_proc = ProcessorFrame(class_name="PreprocessingVehicle", num_processors=num_preps, order=1)
        self.preprocessors_proc.set_params(params)
        self.preprocessors_proc.init()

    def _init_detectors(self, params: list[dict]):
        num_det = len(params)
        self.detectors_proc = ProcessorStep(class_name="ObjectDetectorYolo", num_processors=num_det, order=2)
        self.detectors_proc.set_params(params)
        self.detectors_proc.init()

    def _init_trackers(self, params: list[dict]):
        num_trackers = len(params)
        self.trackers_proc = ProcessorStep(class_name="ObjectTrackingBotsort", num_processors=num_trackers, order=3)
        self.trackers_proc.set_params(params)
        self.trackers_proc.init(encoders=self.encoders)

    def _init_encoders(self, tracker_params_list: list[dict]):
        self.encoders = {}
        for tracker_params in tracker_params_list:
            path = tracker_params.get("tracker_onnx", "osnet_ain_x1_0_M.onnx")
            if path not in self.encoders:
                # Lazy import to avoid circular imports during module load time
                from object_tracker.trackers.onnx_encoder import OnnxEncoder
                self.encoders[path] = OnnxEncoder(path)

    def _init_mc_trackers(self, params: list[dict]):
        num_trackers = len(params)
        self.mc_trackers_proc = ProcessorStep(class_name="ObjectMultiCameraTracking", num_processors=num_trackers, order=4)
        self.mc_trackers_proc.set_params(params)
        self.mc_trackers_proc.init(encoders=self.encoders)
