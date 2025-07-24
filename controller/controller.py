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
        self.sources = []
        self.credentials = dict()
        self.database_config = dict()
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.source_last_processed_frame_id = dict()
        self.preprocessors = []
        self.detectors = []
        self.trackers = []
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

    def is_running(self):
        return self.run_flag

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Get new frames from all sources
            captured_frames = []
            all_sources_finished = True

            for source in self.sources:
                frames = source.get_frames()
                source.insert_debug_info_by_id(self.debug_info.setdefault("sources", {}))

                if len(frames) == 0:
                    if not source.is_finished():
                        all_sources_finished = False
                else:
                    all_sources_finished = False
                    captured_frames.extend(frames)

            if self.autoclose and all_sources_finished:
                self.run_flag = False

            if self.run_flag:
                for source in self.sources:
                    if not source.is_running():
                        source.start()

            complete_capture_it = timer()

            preprocessing_frames = []
            for capture_frame in captured_frames:
                is_preprocessor_found = False
                for preprocessor in self.preprocessors:
                    source_ids = preprocessor.get_source_ids()
                    if capture_frame.source_id in source_ids:
                        preprocessor.put(capture_frame)
                        is_preprocessor_found = True

                    if is_preprocessor_found:
                        break

                if not is_preprocessor_found:
                    preprocessing_frames.append(capture_frame)

            for preprocessor in self.preprocessors:
                prep_result = preprocessor.get()
                if prep_result:
                    preprocessing_frames.append(prep_result)
                preprocessor.insert_debug_info_by_id(self.debug_info.setdefault("preprocessors", {}))

            processing_frames = []
            dropped_frames = []

            detection_results = []
            for frame in preprocessing_frames:
                is_detector_found = False
                for detector in self.detectors:
                    source_ids = detector.get_source_ids()
                    if frame.source_id in source_ids:
                        detector.put(frame)
                        is_detector_found = True

                    if is_detector_found:
                        break

                if not is_detector_found:
                    det_res = DetectionResultList()
                    det_res.source_id = frame.source_id
                    det_res.frame_id = frame.frame_id
                    det_res.time_stamp = frame.time_stamp

                    detection_results.append([det_res, frame])
                    processing_frames.append(frame)

            for detector in self.detectors:
                det_result = detector.get()
                if det_result:
                    detection_results.append(det_result)

                detector.insert_debug_info_by_id(self.debug_info.setdefault("detectors", {}))
            complete_detection_it = timer()

            # Process trackers
            tracking_results = []
            for det_result, image in detection_results:
                is_tracker_found = False
                for tracker in self.trackers:
                    source_ids = tracker.get_source_ids()
                    if image.source_id in source_ids:
                        is_tracker_found = True
                        tracker.put((det_result, image))

                        dropped_ids = tracker.get_dropped_ids()
                        if len(dropped_ids) > 0:
                            dropped_frames.extend(dropped_ids)
                        break
                    if is_tracker_found:
                        break

                if not is_tracker_found:
                    tracking_result = TrackingResultList()
                    tracking_result.frame_id = image.frame_id
                    tracking_result.source_id = image.source_id
                    tracking_result.time_stamp = datetime.datetime.now()
                    tracking_result.generate_from(det_result)

                    tracking_results = tracking_result
                    self.obj_handler.put((tracking_result, image))
                    self.source_last_processed_frame_id[image.source_id] = image.frame_id

                    processing_frames.append(image)

            if self.multicam_reid_enabled:
                track_infos = []
                #if not any(t.queue_out.empty() for t in self.trackers):
                for tracker in self.trackers:
                    track_info = tracker.get()
                    if track_info:
                        tracking_result, image = track_info
                        tracking_results = tracking_result
                        track_infos.append((tracking_result, image))
                        processing_frames.append(image)

                # Process multi camera tracking
                # NOTE: This is a temporary solution which adds
                # multi camera track id to `tracking_data` dict
                if track_infos:
                    self.mc_tracker.put(track_infos)

                mc_track_infos = self.mc_tracker.get()
                if mc_track_infos:
                    for i, track_info in enumerate(mc_track_infos):
                        tracking_result, image = track_info
                        # print(f"Global ids in cam {i}: {[t.tracking_data['global_id'] for t in tracking_result.tracks]}")

                        self.obj_handler.put((tracking_result, image))
                        self.source_last_processed_frame_id[image.source_id] = image.frame_id
            else:
                for tracker in self.trackers:
                    track_info = tracker.get()
                    if track_info:
                        tracking_result, image = track_info
                        tracking_results = tracking_result
                        self.obj_handler.put((tracking_result, image))
                        self.source_last_processed_frame_id[image.source_id] = image.frame_id
                        processing_frames.append(image)

            for tracker in self.trackers:
                tracker.insert_debug_info_by_id(self.debug_info.setdefault("trackers", {}))

            complete_tracking_it = timer()

            events = dict()
            events = self.events_detectors_controller.get()
            # print(events)
            if events:
                self.events_processor.put(events)
            complete_processing_it = timer()


            # Get all dropped images
            for detector in self.detectors:
                dropped_ids = detector.get_dropped_ids()
                if len(dropped_ids) > 0:
                    dropped_frames.extend(dropped_ids)

            for tracker in self.trackers:
                dropped_ids = tracker.get_dropped_ids()
                if len(dropped_ids) > 0:
                    dropped_frames.extend(dropped_ids)

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
        for source in self.sources:
            source.start()
        for preprocessor in self.preprocessors:
            preprocessor.start()
        for detector in self.detectors:
            detector.start()
        for tracker in self.trackers:
            tracker.start()

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
        for tracker in self.trackers:
            tracker.stop()
        for detector in self.detectors:
            detector.stop()
        for preprocessor in self.preprocessors:
            preprocessor.stop()
        for source in self.sources:
            source.stop()
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

        self._init_captures(self.params.get('sources',list()))
        self._init_preprocessors(self.params.get('preprocessors', list()))
        self._init_detectors(self.params.get('detectors',list()))
        self._init_encoders(self.params.get('trackers', list()))
        self._init_trackers(self.params.get('trackers', list()))
        self._init_mc_tracker()

        multicam_reid = self.params['controller'].get("multicam_reid", False)
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

        self.__init_object_handler(self.db_controller, params['objects_handler'])
        self._init_events_detectors(self.params['events_detectors'])
        self._init_events_detectors_controller(self.params['events_detectors'])
        self._init_events_processor(self.params['events_processor'])

        self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
        self.fps = self.params['controller'].get("fps", self.fps)
        self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
        self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
        self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
        self.class_names = self.params['controller'].get("class_names", list())
        self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
        self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
        self.auto_restart = self.params['controller'].get("max_memory_usage_mb", self.auto_restart)

    def init_main_window(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self._init_visualizer(self.params['visualizer'])



    def release(self):
        self.stop()

        for tracker in self.trackers:
            tracker.release()
        for detector in self.detectors:
            detector.release()
        for preprocessor in self.preprocessors:
            preprocessor.release()
        for source in self.sources:
            source.release()
        print('Everything in controller released')

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

    def _init_captures(self, params):
        num_sources = len(params)
        for i in range(num_sources):
            src_params = params[i]
            camera_creds = self.credentials["sources"].get(src_params["camera"], None)
            if camera_creds and (not src_params.get("username", None) or not src_params.get("password", None)):
                src_params["username"] = camera_creds["username"]
                src_params["password"] = camera_creds["password"]
            camera = capture.VideoCapture()
            camera.set_params(**src_params)
            camera.init()
            self.sources.append(camera)
            for source_id, source_name in zip(camera.source_ids, camera.source_names):
                self.source_id_name_table[source_id] = source_name
                self.source_video_duration[source_id] = camera.video_duration
                self.source_last_processed_frame_id[source_id] = 0

    def _init_preprocessors(self, params):
        num_preps = len(params)
        for i in range(num_preps):
            prep_params = params[i]

            preprocessor = preprocessing.PreprocessingVehicle()  # Todo: need module selection by config
            preprocessor.set_params(**prep_params)
            preprocessor.set_id(i)
            preprocessor.init()
            self.preprocessors.append(preprocessor)

    def _init_detectors(self, params):
        num_det = len(params)
        for i in range(num_det):
            det_params = params[i]

            detector = object_detection_yolo.ObjectDetectorYolo()
            detector.set_params(**det_params)
            detector.set_id(i)
            detector.init()
            self.detectors.append(detector)

    def _init_trackers(self, params):
        num_trackers = len(params)

        for i in range(num_trackers):
            tracker_params = params[i]
            encoder = self.encoders[tracker_params.get("tracker_onnx", "osnet_ain_x1_0_M.onnx")]
            tracker = object_tracking_botsort.ObjectTrackingBotsort([encoder])
            tracker.set_params(**tracker_params)
            tracker.init()
            self.trackers.append(tracker)
    
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
        self.cam_events_detector = CamEventsDetector(self.sources)
        self.cam_events_detector.set_params(**params['CamEventsDetector'])
        self.cam_events_detector.init()

        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params['FieldOfViewEventsDetector'])
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params['ZoneEventsDetector'])
        self.zone_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector)
        for source in self.sources:
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
        for source in self.sources:
            source.calc_memory_consumption()
            comp_debug_info = source.insert_debug_info_by_id(self.debug_info.setdefault("sources", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

        for preprocessor in self.preprocessors:
            preprocessor.calc_memory_consumption()
            comp_debug_info = preprocessor.insert_debug_info_by_id(self.debug_info.setdefault("preprocessors", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

        for detector in self.detectors:
            detector.calc_memory_consumption()
            comp_debug_info = detector.insert_debug_info_by_id(self.debug_info.setdefault("detectors", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

        for tracker in self.trackers:
            tracker.calc_memory_consumption()
            comp_debug_info = tracker.insert_debug_info_by_id(self.debug_info.setdefault("trackers", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]

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
