import threading
import capture
import preprocessing
from object_detector import object_detection_yolo
from object_detector import object_detection_yolo_mp
from object_detector.object_detection_base import DetectionResultList
from object_tracker import object_tracking_botsort
from object_tracker.tracking_results import TrackingResultList
# from object_tracker.trackers.bot_sort import Encoder
from object_tracker.trackers.track_encoder import TrackEncoder
from object_tracker.trackers.onnx_encoder import OnnxEncoder
from objects_handler import objects_handler
from capture.video_capture_base import CaptureImage
import time
from timeit import default_timer as timer
from visualization_modules.visualizer import Visualizer
from database_controller.db_adapter_objects import DatabaseAdapterObjects
from database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from events_control.events_processor import EventsProcessor
from database_controller.database_controller_pg import DatabaseControllerPg
from events_control.events_controller import EventsDetectorsController
from events_detectors.cam_events_detector import CamEventsDetector
from events_detectors.fov_events_detector import FieldOfViewEventsDetector
from events_detectors.zone_events_detector import ZoneEventsDetector
import json
from object_multi_camera_tracker.custom_object_tracking import ObjectMultiCameraTracking
import datetime
import pprint
import copy
from core import ProcessorBase, ProcessorSource, ProcessorStep, ProcessorFrame


try:
    from PyQt6.QtWidgets import QMainWindow
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QMainWindow
    pyqt_version = 5

class Controller:
    def __init__(self):
        self.main_window = None
        # self.application = application
        self.control_thread = threading.Thread(target=self.run)
        self.params = None
        self.credentials = dict()
        self.database_config = dict()
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.source_last_processed_frame_id = dict()

        self.pipeline = [[{}]]

        self.sources_proc = None
        self.preprocessors_proc = None
        self.detector_proc = None
        self.tracker_proc = None
        self.obj_handler = None
        self.visualizer = None
        self.pyqt_slots = None
        self.pyqt_signals = None
        self.fps = 5
        self.show_main_gui = True
        self.show_journal = False
        self.enable_close_from_gui = True
        self.memory_periodic_check_sec = 60*15
        self.max_memory_usage_mb = 1024*16
        self.auto_restart = True


        self.events_detectors_controller = None
        self.events_processor = None
        self.cam_events_detector = None
        self.fov_events_detector = None
        self.zone_events_detector = None

        self.db_controller = None
        self.db_adapter_obj = None
        self.db_adapter_cam_events = None
        self.db_adapter_fov_events = None
        self.db_adapter_zone_events = None
        self.class_names = list()

        #self.captured_frames: list[CaptureImage] = []
        #self.preprocessed_frames: list[CaptureImage] = []
        #self.detection_results: list[DetectionResultList] = []
        #self.tracking_results: list[TrackingResultList] = []
        self.run_flag = False
        self.restart_flag = False

        self.gui_enabled = True
        self.autoclose = False
        self.multicam_reid_enabled = False

        self.current_main_widget_size = [1920, 1080]

        self.debug_info = dict()

    def add_channel(self):
        self.add_module("source", None)
        self.add_module("detector", None)
        self.add_module("tracker", None)

    def add_module(self, module_type: str, params: dict):
        if module_type == "source":
            camera = capture.VideoCapture()
            if params:
                camera.set_params(params)
            camera.init()
            self.sources.append(camera)
            if camera.source_ids is not None and camera.source_names is not None:
                for source_id, source_name in zip(camera.source_ids, camera.source_names):
                    self.source_id_name_table[source_id] = source_name
                    self.source_video_duration[source_id] = camera.video_duration
                    self.source_last_processed_frame_id[source_id] = 0
            self._init_events_detectors(self.params.get('events_detectors', dict()))
            self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
            self.params['sources'].append(camera.get_params())

        elif module_type == "detector":
            detector = object_detection_yolo.ObjectDetectorYolo()
            if params:
                detector.set_params(params)
            obj_max_id = 0
            for obj in self.detectors:
                if obj.get_id() > obj_max_id:
                    obj_max_id = obj.get_id()
            obj_max_id += 1
            detector.set_id(obj_max_id)
            detector.init()
            self.detectors.append(detector)
            self.params['detectors'].append(detector.get_params())
        elif module_type == "tracker":
            if params:
                tracker_params = params
            else:
                tracker_params = dict()
            path = tracker_params.get("tracker_onnx", "osnet_ain_x1_0_M.onnx")
            if path not in self.encoders:
                encoder = OnnxEncoder(path)
                self.encoders[path] = encoder
            encoder = self.encoders[tracker_params.get("tracker_onnx", "osnet_ain_x1_0_M.onnx")]
            tracker = object_tracking_botsort.ObjectTrackingBotsort([encoder])
            if params:
                tracker.set_params(**tracker_params)
            tracker.init()
            self.trackers.append(tracker)
            self.params['trackers'].append(tracker.get_params())

            is_mc_started = self.mc_tracker.run_flag
            self._init_mc_tracker()
            if is_mc_started:
                self.mc_tracker.start()

    def del_module(self, module_type: str, id: int):
        if module_type == "source":
            for obj in self.sources:
                if obj.get_id() == id:
                    self.sources.remove(obj)
                    self._init_events_detectors(self.params.get('events_detectors', dict()))
                    self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
                    break
        elif module_type == "detector":
            for obj in self.detectors:
                if obj.get_id() == id:
                    self.detectors.remove(obj)
                    break
        elif module_type == "tracker":
            for obj in self.trackers:
                if obj.get_id() == id:
                    self.trackers.remove(obj)
                    is_mc_started = self.mc_tracker.run_flag
                    self._init_mc_tracker()
                    if is_mc_started:
                        self.mc_tracker.start()
                    break

    def is_running(self):
        return self.run_flag

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Get new frames from all sources
            captured_frames = []
            processing_frames = []
            all_sources_finished = True

            captured_frames, all_sources_finished = self.sources_proc.process()
            self.sources_proc.insert_debug_info_by_id("sources", self.debug_info)

            if self.autoclose and all_sources_finished:
                self.run_flag = False

            if self.run_flag:
                self.sources_proc.run_sources()

            complete_capture_it = timer()

            preprocessing_frames = []
            preprocessing_frames = self.preprocessors_proc.process(captured_frames)
            self.preprocessors_proc.insert_debug_info_by_id("preprocessors", self.debug_info)
            dropped_frames = []

            #detection_results = []
            detection_results = self.detector_proc.process(preprocessing_frames)
            self.detector_proc.insert_debug_info_by_id("detectors", self.debug_info)
            complete_detection_it = timer()

            # Process trackers
            tracking_results = []

            tracking_results = self.tracker_proc.process(detection_results)
            self.detector_proc.insert_debug_info_by_id("trackers", self.debug_info)

            if self.multicam_reid_enabled:
                # Process multi camera tracking
                # NOTE: This is a temporary solution which adds
                # multi camera track id to `tracking_data` dict
                if tracking_results:
                    self.mc_tracker.put(tracking_results)

                mc_track_infos = self.mc_tracker.get()
                if mc_track_infos:
                    for i, track_info in enumerate(mc_track_infos):
                        tracking_result, image = track_info
                        # print(f"Global ids in cam {i}: {[t.tracking_data['global_id'] for t in tracking_result.tracks]}")

                        self.obj_handler.put(track_info)
                        self.source_last_processed_frame_id[image.source_id] = image.frame_id
                        processing_frames.append(image)
            else:
                for track_info in tracking_results:
                    tracking_result, image = track_info
                    self.obj_handler.put(track_info)
                    processing_frames.append(image)
                    self.source_last_processed_frame_id[image.source_id] = image.frame_id

            complete_tracking_it = timer()

            events = dict()
            events = self.events_detectors_controller.get()
            # print(events)
            if events:
                self.events_processor.put(events)
            complete_processing_it = timer()


            # Get all dropped images
            dropped_frames.extend(self.detector_proc.get_dropped_ids())
            dropped_frames.extend(self.tracker_proc.get_dropped_ids())

            if not self.debug_info.get("controller", None) or not self.debug_info["controller"].get("timestamp", None) or ((datetime.datetime.now() - self.debug_info["controller"]["timestamp"]).total_seconds() > self.memory_periodic_check_sec):
                self.collect_memory_consumption()
                pprint.pprint(self.debug_info)

                if self.debug_info.get("controller", None):
                    total_memory_usage_mb = self.debug_info["controller"].get("total_memory_usage_mb", None)
                    if total_memory_usage_mb and total_memory_usage_mb >= self.max_memory_usage_mb:
                        print(f"total_memory_usage={total_memory_usage_mb:.2f} Mb max_memory_usage_mb={self.max_memory_usage_mb:.2f} Mb")
                        pprint.pprint(self.debug_info)
                        params = copy.deepcopy(self.params)
                        if self.auto_restart:
                            self.restart_flag = True
                        self.run_flag = False
                        continue


            if self.show_main_gui and self.gui_enabled:
                objects = []
                for i in range(len(self.visualizer.source_ids)):
                    objects.append(self.obj_handler.get('active', self.visualizer.source_ids[i]))
                complete_read_objects_it = timer()
                self.visualizer.update(processing_frames, self.source_last_processed_frame_id, objects, dropped_frames, self.debug_info)
            else:
                complete_read_objects_it = timer()

            end_it = timer()
            elapsed_seconds = end_it - begin_it

            if self.fps:
                sleep_seconds = 1. / self.fps - elapsed_seconds
                if sleep_seconds <= 0.0:
                    sleep_seconds = 0.001
            else:
                sleep_seconds = 0.03

            #print(f"Time: cap[{complete_capture_it-begin_it}], det[{complete_detection_it-complete_capture_it}], track[{complete_tracking_it-complete_detection_it}], events[{complete_processing_it-complete_tracking_it}]], "
            #       f"read=[{complete_read_objects_it-complete_processing_it}], vis[{end_it-complete_read_objects_it}] = {end_it-begin_it} secs, sleep {sleep_seconds} secs")
            time.sleep(sleep_seconds)

    def start(self):
        self.sources_proc.start()
        self.preprocessors_proc.start()
        self.detector_proc.start()
        self.tracker_proc.start()
        if self.multicam_reid_enabled:
            self.mc_tracker.start()
        self.obj_handler.start()
        if self.visualizer:
            self.visualizer.start()
        self.db_controller.connect()
        self.db_adapter_obj.start()
        self.db_adapter_zone_events.start()
        self.db_adapter_fov_events.start()
        self.db_adapter_cam_events.start()
        self.zone_events_detector.start()
        self.cam_events_detector.start()
        self.fov_events_detector.start()
        self.events_detectors_controller.start()
        self.events_processor.start()
        self.run_flag = True
        self.control_thread.start()

    def stop(self):
        # self._save_video_duration()
        self.run_flag = False
        self.control_thread.join()
        self.events_processor.stop()
        self.events_detectors_controller.stop()
        self.cam_events_detector.stop()
        self.fov_events_detector.stop()
        self.zone_events_detector.stop()
        self.visualizer.stop()
        self.obj_handler.stop()
        self.db_adapter_cam_events.stop()
        self.db_adapter_fov_events.stop()
        self.db_adapter_zone_events.stop()
        self.db_adapter_obj.stop()
        self.db_controller.disconnect()
        self.tracker_proc.stop()
        self.detector_proc.stop()
        self.preprocessors_proc.stop()
        self.sources_proc.stop()
        if self.multicam_reid_enabled:
            self.mc_tracker.stop()
        print('Everything in controller stopped')

    def init(self, params):
        self.params = params

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
        except FileNotFoundError as ex:
            pass

        self._init_sources(self.params.get('sources', list()))
        self._init_preprocessors(self.params.get('preprocessors', list()))
        self._init_detectors(self.params.get('detectors',list()))
        self._init_encoders(self.params.get('trackers', list()))
        self._init_trackers(self.params.get('trackers', list()))
        self._init_mc_tracker()

        multicam_reid = self.params.get('controller', dict()).get("multicam_reid", False)
        if multicam_reid:
            for tracker_params in self.params.get('trackers', list()):
                botsort_cfg = tracker_params.get("botsort_cfg", None)
                if not botsort_cfg or botsort_cfg.get("with_reid", False) == False:
                    multicam_reid = False
                    break
        self.multicam_reid_enabled = multicam_reid

        database_creds = self.credentials.get("database", None)
        if not database_creds:
            database_creds = dict()

        try:
            with open("database_config.json") as data_config_file:
                self.database_config = json.load(data_config_file)
        except FileNotFoundError as ex:
            pass

        database_creds["user_name"] = database_creds.get("user_name", "postgres")
        database_creds["password"] = database_creds.get("password", "")
        database_creds["database_name"] = database_creds.get("database_name", "evil_eye_db")
        database_creds["host_name"] = database_creds.get("host_name", "localhost")
        database_creds["port"] = database_creds.get("port", 5432)
        database_creds["default_database_name"] = database_creds.get("default_database_name", "postgres")
        database_creds["default_password"] = database_creds.get("default_password", "")
        database_creds["default_user_name"] = database_creds.get("default_user_name", "postgres")
        database_creds["default_host_name"] = database_creds.get("default_host_name", "localhost")
        database_creds["default_port"] = database_creds.get("default_port", 5432)

        self.database_config["database"]["user_name"] = self.database_config["database"].get("user_name", database_creds["user_name"])
        self.database_config["database"]["password"] = self.database_config["database"].get("password", database_creds["password"])
        self.database_config["database"]["database_name"] = self.database_config["database"].get("database_name", database_creds["database_name"])
        self.database_config["database"]["host_name"] = self.database_config["database"].get("host_name", database_creds["host_name"])
        self.database_config["database"]["port"] = self.database_config["database"].get("port", database_creds["port"])
        self.database_config["database"]["default_database_name"] = self.database_config["database"].get("default_database_name", database_creds["default_database_name"])
        self.database_config["database"]["default_password"] = self.database_config["database"].get("default_password", database_creds["default_password"])
        self.database_config["database"]["default_user_name"] = self.database_config["database"].get("default_user_name", database_creds["default_user_name"])
        self.database_config["database"]["default_host_name"] = self.database_config["database"].get("default_host_name", database_creds["default_host_name"])
        self.database_config["database"]["default_port"] = self.database_config["database"].get("default_port", database_creds["default_port"])

        self._init_db_controller(self.database_config['database'], system_params=self.params)
        self._init_db_adapters(self.database_config['database_adapters'])

        self.__init_object_handler(self.db_controller, params.get('objects_handler', dict()))
        self._init_events_detectors(self.params.get('events_detectors', dict()))
        self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
        self._init_events_processor(self.params.get('events_processor', dict()))

        if 'controller' in self.params.keys():
            self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
            self.fps = self.params['controller'].get("fps", self.fps)
            self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
            self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
            self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
            self.class_names = self.params['controller'].get("class_names", list())
            self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
            self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
            self.auto_restart = self.params['controller'].get("auto_restart", self.auto_restart)

    def init_main_window(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self._init_visualizer(self.params['visualizer'])

    def release(self):
        self.stop()

        #for tracker in self.trackers:
        #    tracker.release()
        self.tracker_proc.release()
        self.detector_proc.release()
        #for detector in self.detectors:
        #    detector.release()
        self.preprocessors_proc.release()
        #for preprocessor in self.preprocessors:
        #    preprocessor.release()
        self.sources_proc.release()
        #for source in self.sources:
        #    source.release()
        print('Everything in controller released')

    def save_params(self, params: dict):
        self.params['controller'] = dict()
        self.params['controller']["autoclose"] = self.autoclose
        self.params['controller']["fps"] = self.fps
        self.params['controller']["show_main_gui"] = self.show_main_gui
        self.params['controller']["show_journal"] = self.show_journal
        self.params['controller']["enable_close_from_gui"] = self.enable_close_from_gui
        self.params['controller']["class_names"] = self.class_names
        self.params['controller']["memory_periodic_check_sec"] = self.memory_periodic_check_sec
        self.params['controller']["max_memory_usage_mb"] = self.max_memory_usage_mb
        self.params['controller']["auto_restart"] = self.auto_restart

        self.params['sources'] = list()
        self.sources_proc.get_params(self.params['sources'])

        self.params['preprocessors'] = list()
        self.preprocessors_proc.get_params(self.params['preprocessors'])

        self.params['detectors'] = list()
        self.detector_proc.get_params(self.params['detectors'])

        self.params['trackers'] = list()
        self.tracker_proc.get_params(self.params['trackers'])

        self.params['objects_handler'] = self.obj_handler.get_params()

        self.params['events_detectors'] = dict()
        self.params['events_detectors']['CamEventsDetector'] = self.cam_events_detector.get_params()
        self.params['events_detectors']['FieldOfViewEventsDetector'] = self.fov_events_detector.get_params()
        self.params['events_detectors']['ZoneEventsDetector'] = self.zone_events_detector.get_params()

        self.params['events_processor'] = self.events_processor.get_params()
        # self.params['database'] = self.db_controller.get_params()
        if self.visualizer:
            self.params['visualizer'] = self.visualizer.get_params()
        else:
            self.params['visualizer'] = dict()

    def set_current_main_widget_size(self, width, height):
        self.current_main_widget_size = [width, height]
        self.visualizer.set_current_main_widget_size(width, height)

    def __init_object_handler(self, db_controller, params):
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=db_controller, db_adapter=self.db_adapter_obj)
        self.obj_handler.set_params(**params)
        self.obj_handler.init()

    def _init_db_controller(self, params, system_params):
        self.db_controller = DatabaseControllerPg(system_params)
        self.db_controller.set_params(**params)
        self.db_controller.init()

    def _init_db_adapters(self, params):
        self.db_adapter_obj = DatabaseAdapterObjects(self.db_controller)
        self.db_adapter_obj.set_params(**params['DatabaseAdapterObjects'])
        self.db_adapter_obj.init()

        self.db_adapter_cam_events = DatabaseAdapterCamEvents(self.db_controller)
        self.db_adapter_cam_events.set_params(**params['DatabaseAdapterCamEvents'])
        self.db_adapter_cam_events.init()

        self.db_adapter_fov_events = DatabaseAdapterFieldOfViewEvents(self.db_controller)
        self.db_adapter_fov_events.set_params(**params['DatabaseAdapterFieldOfViewEvents'])
        self.db_adapter_fov_events.init()

        self.db_adapter_zone_events = DatabaseAdapterZoneEvents(self.db_controller)
        self.db_adapter_zone_events.set_params(**params['DatabaseAdapterZoneEvents'])
        self.db_adapter_zone_events.init()

    def _init_sources(self, params):
        num_sources = len(params)
        self.sources_proc = ProcessorSource(class_name="VideoCapture", num_processors=num_sources, order=0)
        for i in range(num_sources):
            src_params = params[i]
            camera_creds = self.credentials["sources"].get(src_params["camera"], None)
            if camera_creds and (not src_params.get("username", None) or not src_params.get("password", None)):
                src_params["username"] = camera_creds["username"]
                src_params["password"] = camera_creds["password"]

        self.sources_proc.set_params(params)
        self.sources_proc.init()
        for j in range(num_sources):
            source = self.sources_proc.get_processors()[j]
            for source_id, source_name in zip(source.source_ids, source.source_names):
                self.source_id_name_table[source_id] = source_name
                self.source_video_duration[source_id] = source.video_duration
                self.source_last_processed_frame_id[source_id] = 0

    def _init_preprocessors(self, params):
        num_preps = len(params)
        self.preprocessors_proc = ProcessorFrame(class_name="PreprocessingVehicle", num_processors=num_preps, order=1)
        self.preprocessors_proc.set_params(params)
        self.preprocessors_proc.init()

    def _init_detectors(self, params):
        num_det = len(params)
        self.detector_proc = ProcessorStep(class_name="ObjectDetectorYolo", num_processors=num_det, order=2)
        self.detector_proc.set_params(params)
        self.detector_proc.init()

    def _init_trackers(self, params):
        num_trackers = len(params)
        self.tracker_proc = ProcessorStep(class_name="ObjectTrackingBotsort", num_processors=num_trackers, order=3)
        self.tracker_proc.set_params(params)
        self.tracker_proc.init(encoders=self.encoders)
    
    def _init_encoders(self, params):
        num_trackers = len(params)
        self.encoders = {}

        for i in range(num_trackers):
            tracker_params = params[i]
            path = tracker_params.get("tracker_onnx", "osnet_ain_x1_0_M.onnx")
            
            if path not in self.encoders:
                encoder = OnnxEncoder(path)
                self.encoders[path] = encoder
    
    def _init_mc_tracker(self):
        num_of_cameras = len(self.params.get('sources', list()))
        self.mc_tracker = ObjectMultiCameraTracking(
            num_of_cameras, 
            list(self.encoders.values())
        )
        self.mc_tracker.init()

    def _init_events_detectors(self, params):
        self.cam_events_detector = CamEventsDetector(self.sources_proc.get_processors())
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
        self.zone_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector)
        for source in self.sources_proc.get_processors():
            source.subscribe(self.cam_events_detector)

    def _init_events_detectors_controller(self, params):
        detectors = [self.cam_events_detector, self.fov_events_detector, self.zone_events_detector]
        self.events_detectors_controller = EventsDetectorsController(detectors)
        self.events_detectors_controller.set_params(**params)
        self.events_detectors_controller.init()

    def _init_events_processor(self, params):
        db_adapters = [self.db_adapter_fov_events, self.db_adapter_cam_events, self.db_adapter_zone_events]
        self.events_processor = EventsProcessor(db_adapters, self.db_controller)
        self.events_processor.set_params(**params)
        self.events_processor.init()

    def _init_visualizer(self, params):
        self.gui_enabled = params.get("gui_enabled", True)
        self.visualizer = Visualizer(self.pyqt_slots, self.pyqt_signals)
        self.visualizer.set_params(**params)
        self.visualizer.source_id_name_table = self.source_id_name_table
        self.visualizer.source_video_duration = self.source_video_duration
        self.visualizer.init()

    def collect_memory_consumption(self):
        total_memory_usage = 0
        self.sources_proc.calc_memory_consumption()
        total_memory_usage += self.sources_proc.get_memory_usage()

        self.preprocessors_proc.calc_memory_consumption()
        total_memory_usage += self.preprocessors_proc.get_memory_usage()

        self.detector_proc.calc_memory_consumption()
        total_memory_usage += self.detector_proc.get_memory_usage()

        self.tracker_proc.calc_memory_consumption()
        total_memory_usage += self.tracker_proc.get_memory_usage()

        self.mc_tracker.calc_memory_consumption()
        comp_debug_info = self.mc_tracker.insert_debug_info_by_id(self.debug_info.setdefault("mc_tracker", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.obj_handler.calc_memory_consumption()
        comp_debug_info = self.obj_handler.insert_debug_info_by_id(self.debug_info.setdefault("obj_handler", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.events_processor.calc_memory_consumption()
        comp_debug_info = self.events_processor.insert_debug_info_by_id(self.debug_info.setdefault("events_processor", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.events_detectors_controller.calc_memory_consumption()
        comp_debug_info = self.events_detectors_controller.insert_debug_info_by_id(self.debug_info.setdefault("events_detectors_controller", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.cam_events_detector.calc_memory_consumption()
        comp_debug_info = self.cam_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("cam_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.fov_events_detector.calc_memory_consumption()
        comp_debug_info = self.fov_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("fov_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.zone_events_detector.calc_memory_consumption()
        comp_debug_info = self.zone_events_detector.insert_debug_info_by_id(self.debug_info.setdefault("zone_events_detector", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.visualizer.calc_memory_consumption()
        comp_debug_info = self.visualizer.insert_debug_info_by_id(self.debug_info.setdefault("visualizer", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.db_controller.calc_memory_consumption()
        comp_debug_info = self.db_controller.insert_debug_info_by_id(self.debug_info.setdefault("db_controller", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.db_adapter_obj.calc_memory_consumption()
        comp_debug_info = self.db_adapter_obj.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_obj", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.db_adapter_cam_events.calc_memory_consumption()
        comp_debug_info = self.db_adapter_cam_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_cam_events", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.db_adapter_fov_events.calc_memory_consumption()
        comp_debug_info = self.db_adapter_fov_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_fov_events", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.db_adapter_zone_events.calc_memory_consumption()
        comp_debug_info = self.db_adapter_zone_events.insert_debug_info_by_id(self.debug_info.setdefault("db_adapter_zone_events", {}))
        total_memory_usage += comp_debug_info["memory_measure_results"]

        self.debug_info["controller"] = dict()
        self.debug_info["controller"]["timestamp"] = datetime.datetime.now()
        self.debug_info["controller"]["total_memory_usage_mb"] = total_memory_usage/(1024.0*1024.0)


    # def _save_video_duration(self):
    #     self.db_controller.update_video_dur(self.source_video_duration)
