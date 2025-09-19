import threading
import os
import importlib
import inspect
from pathlib import Path
from evileye.capture import video_capture
from evileye.object_detector import object_detection_yolo
from evileye.object_tracker import object_tracking_botsort
from evileye.object_tracker.trackers.onnx_encoder import OnnxEncoder
from evileye.objects_handler import objects_handler
import time
from timeit import default_timer as timer
from evileye.visualization_modules.visualizer import Visualizer
from evileye.database_controller.db_adapter_objects import DatabaseAdapterObjects
from evileye.database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from evileye.database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from evileye.events_control.events_processor import EventsProcessor
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_detectors.cam_events_detector import CamEventsDetector
from evileye.events_detectors.fov_events_detector import FieldOfViewEventsDetector
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
import json
import datetime
import pprint
import copy
import math
from evileye.core import ProcessorSource, ProcessorStep, ProcessorFrame
from evileye.pipelines import PipelineSurveillance


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

        self.pipeline = None

        self.obj_handler = None
        self.visualizer = None
        self.pyqt_slots = None
        self.pyqt_signals = None
        self.fps = 30
        self.show_main_gui = True
        self.show_journal = False
        self.enable_close_from_gui = True
        self.memory_periodic_check_sec = 60*15
        self.max_memory_usage_mb = 1024*16
        self.show_memory_usage = False
        self.auto_restart = True
        self.use_database = True  # Default to True for backward compatibility

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
        self.class_names = [
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
            "traffic light",
            "fire hydrant",
            "stop sign",
            "parking meter",
            "bench",
            "bird",
            "cat",
            "dog",
            "horse",
            "sheep",
            "cow",
            "elephant",
            "bear",
            "zebra",
            "giraffe",
            "backpack",
            "umbrella",
            "handbag",
            "tie",
            "suitcase",
            "frisbee",
            "skis",
            "snowboard",
            "sports ball",
            "kite",
            "baseball bat",
            "baseball glove",
            "skateboard",
            "surfboard",
            "tennis racket",
            "bottle",
            "wine glass",
            "cup",
            "fork",
            "knife",
            "spoon",
            "bowl",
            "banana",
            "apple",
            "sandwich",
            "orange",
            "broccoli",
            "carrot",
            "hot dog",
            "pizza",
            "donut",
            "cake",
            "chair",
            "couch",
            "potted plant",
            "bed",
            "dining table",
            "toilet",
            "tv",
            "laptop",
            "mouse",
            "remote",
            "keyboard",
            "cell phone",
            "microwave",
            "oven",
            "toaster",
            "sink",
            "refrigerator",
            "book",
            "clock",
            "vase",
            "scissors",
            "teddy bear",
            "hair drier",
            "toothbrush"
        ]

        self.run_flag = False
        self.restart_flag = False

        self.gui_enabled = True
        self.autoclose = False
        #self.multicam_reid_enabled = False

        self.current_main_widget_size = [1920, 1080]

        self.debug_info = dict()

    def get_params(self):
        return self.params

    def add_pipeline(self, pipeline_type):
        pass

    def del_pipeline(self, pipeline_type):
        pass

    def add_processor(self, processor_name: str, processor_class: str, params: dict):
        pass

    def del_processor(self, processor_name: str, id: int):
        pass

    def is_running(self):
        return self.run_flag

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Process pipeline: sources -> preprocessors -> detectors -> trackers -> mc_trackers
            self.pipeline.process()
            all_sources_finished = self.pipeline.check_all_sources_finished()

            pipeline_results = self.pipeline.peek_latest_result()

            #mc_tracking_results = pipeline_results.get("mc_trackers", [])
            mc_tracking_results = pipeline_results.get(self.pipeline.get_final_results_name(), [])

            # Insert debug info from pipeline components
            self.pipeline.insert_debug_info_by_id(self.debug_info)

            if self.autoclose and all_sources_finished:
                self.run_flag = False

            complete_capture_it = timer()
            complete_detection_it = timer()
            complete_tracking_it = timer()

            # Process tracking results
            processing_frames = []
            for track_info in mc_tracking_results:
                tracking_result, image = track_info
                self.obj_handler.put(track_info)
                processing_frames.append(image)
                self.source_last_processed_frame_id[image.source_id] = image.frame_id

            events = dict()
            events = self.events_detectors_controller.get()
            # print(events)
            if events:
                self.events_processor.put(events)
            complete_processing_it = timer()

            # Get all dropped images from pipeline
            dropped_frames = self.pipeline.get_dropped_ids()

            if not self.debug_info.get("controller", None) or not self.debug_info["controller"].get("timestamp", None) or ((datetime.datetime.now() - self.debug_info["controller"]["timestamp"]).total_seconds() > self.memory_periodic_check_sec):
                self.collect_memory_consumption()
                if self.show_memory_usage:
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
        # Start pipeline components
        self.pipeline.start()
        
        # Start other components
        self.obj_handler.start()
        if self.visualizer:
            self.visualizer.start()
        
        # Start database components only if database is enabled
        if self.use_database and self.db_controller:
            try:
                self.db_controller.connect()
                self.db_adapter_obj.start()
                self.db_adapter_zone_events.start()
                self.db_adapter_fov_events.start()
                self.db_adapter_cam_events.start()
            except Exception as e:
                print(f"Warning: Database connection failed during start. Disabling database functionality. Reason: {e}")
                self.use_database = False
                self.db_controller = None
        
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
        if self.control_thread.is_alive():
            self.control_thread.join()
        self.events_processor.stop()
        self.events_detectors_controller.stop()
        self.cam_events_detector.stop()
        self.fov_events_detector.stop()
        self.zone_events_detector.stop()
        if self.visualizer:
            self.visualizer.stop()
        self.obj_handler.stop()
        
        # Stop database components only if database is enabled
        if self.use_database and self.db_controller:
            self.db_adapter_cam_events.stop()
            self.db_adapter_fov_events.stop()
            self.db_adapter_zone_events.stop()
            self.db_adapter_obj.stop()
            self.db_controller.disconnect()
        
        # Stop pipeline components
        self.pipeline.stop()
        print('Everything in controller stopped')

    def init(self, params):
        self.params = params

        if 'controller' in self.params.keys():
            self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
            self.fps = self.params['controller'].get("fps", self.fps)
            self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
            self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
            self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
            self.class_names = self.params['controller'].get("class_names", list())
            self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
            self.show_memory_usage = self.params['controller'].get("show_memory_usage", self.show_memory_usage)
            self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
            self.auto_restart = self.params['controller'].get("auto_restart", self.auto_restart)
            self.use_database = self.params['controller'].get("use_database", self.use_database)

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
        except FileNotFoundError as ex:
            pass

        # Initialize processing pipeline (sources, preprocessors, detectors, trackers)
        pipeline_params = self.params.get("pipeline", {})
        pipeline_class_name = pipeline_params.get("pipeline_class")
        
        if pipeline_class_name:
            try:
                self.pipeline = self._create_pipeline_instance(pipeline_class_name)
                print(f"Using pipeline class: {pipeline_class_name}")
            except Exception as e:
                print(f"Warning: Could not create pipeline '{pipeline_class_name}': {e}")
                print("Falling back to default PipelineSurveillance")
                self.pipeline = PipelineSurveillance()
        else:
            print("Warning: No pipeline_class specified in pipeline parameters, using default PipelineSurveillance")
            self.pipeline = PipelineSurveillance()
        
        self.pipeline.set_credentials(self.credentials)
        self.pipeline.set_params(**pipeline_params)
        self.pipeline.init()

        # Fill source maps for visualizer and bookkeeping
        if hasattr(self.pipeline, "get_sources"):
            sources = self.pipeline.get_sources()
            if sources:
                for source in sources:
                    if hasattr(source, 'source_ids') and hasattr(source, 'source_names') and source.source_ids and source.source_names:
                        for source_id, source_name in zip(source.source_ids, source.source_names):
                            self.source_id_name_table[source_id] = source_name
                            if hasattr(source, 'video_duration'):
                                self.source_video_duration[source_id] = source.video_duration
                            self.source_last_processed_frame_id[source_id] = 0

        # Initialize database configuration only if database is enabled
        if self.use_database:
            database_creds = self.credentials.get("database", None)
            if not database_creds:
                database_creds = dict()

            try:
                with open(os.path.join(os.path.dirname(__file__), "..", "database_config.json")) as data_config_file:
                    self.database_config = json.load(data_config_file)
            except FileNotFoundError as ex:
                pass

            database_creds["user_name"] = database_creds.get("user_name", "postgres")
            database_creds["password"] = database_creds.get("password", "")
            database_creds["database_name"] = database_creds.get("database_name", "evil_eye_db")
            database_creds["host_name"] = database_creds.get("host_name", "localhost")
            database_creds["port"] = database_creds.get("port", 5432)
            database_creds["admin_user_name"] = database_creds.get("admin_user_name", "postgres")
            database_creds["admin_password"] = database_creds.get("admin_password", "")

            self.database_config["database"]["user_name"] = self.database_config["database"].get("user_name", database_creds["user_name"])
            self.database_config["database"]["password"] = self.database_config["database"].get("password", database_creds["password"])
            self.database_config["database"]["database_name"] = self.database_config["database"].get("database_name", database_creds["database_name"])
            self.database_config["database"]["host_name"] = self.database_config["database"].get("host_name", database_creds["host_name"])
            self.database_config["database"]["port"] = self.database_config["database"].get("port", database_creds["port"])
            self.database_config["database"]["admin_user_name"] = self.database_config["database"].get("admin_user_name", database_creds["admin_user_name"])
            self.database_config["database"]["admin_password"] = self.database_config["database"].get("admin_password", database_creds["admin_password"])

            if 'database' in self.params.keys():
                self.database_config["database"]['database_name'] = self.params['database'].get('database_name', self.database_config["database"]['database_name'])
                self.database_config["database"]['host_name'] = self.params['database'].get('host_name', self.database_config["database"]['host_name'])
                self.database_config["database"]['port'] = self.params['database'].get('port', self.database_config["database"]['port'])
                self.database_config["database"]['image_dir'] = self.params['database'].get('image_dir', self.database_config["database"]['image_dir'])
                self.database_config["database"]['preview_width'] = self.params['database'].get('preview_width', self.database_config["database"]['preview_width'])
                self.database_config["database"]['preview_height'] = self.params['database'].get('preview_height', self.database_config["database"]['preview_height'])
        else:
            # Initialize empty database config when database is disabled
            self.database_config = {"database": {}, "database_adapters": {}}

        # Initialize database components only if use_database is True
        if self.use_database:
            try:
                self._init_db_controller(self.database_config['database'], system_params=self.params)
                self._init_db_adapters(self.database_config['database_adapters'])
                self._init_object_handler(self.db_controller, params.get('objects_handler', dict()))
                self._init_events_detectors(self.params.get('events_detectors', dict()))
                self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
                self._init_events_processor(self.params.get('events_processor', dict()))
            except Exception as e:
                print(f"Warning: Database is enabled but not accessible. Running without database. Reason: {e}")
                # Fallback to no-database mode
                self.use_database = False
                self.db_controller = None
                self.database_config = {"database": {}, "database_adapters": {}}
                self._init_object_handler_without_db(params.get('objects_handler', dict()))
                self._init_events_detectors_without_db(self.params.get('events_detectors', dict()))
                self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
                self._init_events_processor_without_db(self.params.get('events_processor', dict()))
        else:
            print("Database functionality disabled. Running without database connection.")
            # Initialize minimal components for operation without database
            self._init_object_handler_without_db(params.get('objects_handler', dict()))
            self._init_events_detectors_without_db(self.params.get('events_detectors', dict()))
            self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
            self._init_events_processor_without_db(self.params.get('events_processor', dict()))

    def init_main_window(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self._init_visualizer(self.params['visualizer'])

    def release(self):
        self.stop()
        # Release pipeline components
        self.pipeline.release()
        print('Everything in controller released')

    def update_params(self):
        self.params['controller'] = dict()
        self.params['controller']["autoclose"] = self.autoclose
        self.params['controller']["fps"] = self.fps
        self.params['controller']["show_main_gui"] = self.show_main_gui
        self.params['controller']["show_journal"] = self.show_journal
        self.params['controller']["enable_close_from_gui"] = self.enable_close_from_gui
        self.params['controller']["class_names"] = self.class_names
        self.params['controller']["memory_periodic_check_sec"] = self.memory_periodic_check_sec
        self.params['controller']["show_memory_usage"] = self.show_memory_usage

        self.params['controller']["max_memory_usage_mb"] = self.max_memory_usage_mb
        self.params['controller']["auto_restart"] = self.auto_restart
        self.params['controller']["use_database"] = self.use_database

        # Get pipeline parameters
        pipeline_params = self.pipeline.get_params()
        self.params['pipeline'] = pipeline_params

        self.params['objects_handler'] = self.obj_handler.get_params()

        self.params['events_detectors'] = dict()
        self.params['events_detectors']['CamEventsDetector'] = self.cam_events_detector.get_params()
        self.params['events_detectors']['FieldOfViewEventsDetector'] = self.fov_events_detector.get_params()
        self.params['events_detectors']['ZoneEventsDetector'] = self.zone_events_detector.get_params()

        self.params['events_processor'] = self.events_processor.get_params()
        
        # Only update database config if database is enabled
        if self.use_database and self.db_controller:
            self.database_config = self.db_controller.get_params()

            self.params['database'] = {}
            self.params['database']['database_name'] = self.database_config.get('database_name', 'evil_eye_db')
            self.params['database']['host_name'] = self.database_config.get('host_name', 'localhost')
            self.params['database']['port'] = self.database_config.get('port', 5432)
            self.params['database']['admin_user_name'] = self.database_config.get('admin_user_name', 'postgres')
            self.params['database']['admin_password'] = self.database_config.get('admin_password', '')
            self.params['database']['image_dir'] = self.database_config.get('image_dir', 'EvilEyeData')
            self.params['database']['preview_width'] = self.database_config.get('preview_width', 300)
            self.params['database']['preview_height'] = self.database_config.get('preview_height', 150)
        else:
            # Set empty database config when database is disabled
            self.params['database'] = {}

        if self.visualizer:
            self.params['visualizer'] = self.visualizer.get_params()
        else:
            self.params['visualizer'] = dict()

        # Text configuration is now part of visualizer section
        # No need to add separate text_config here

    def set_current_main_widget_size(self, width, height):
        self.current_main_widget_size = [width, height]
        self.visualizer.set_current_main_widget_size(width, height)

    def _init_object_handler(self, db_controller, params):
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=db_controller, db_adapter=self.db_adapter_obj)
        self.obj_handler.set_params(**params)
        self.obj_handler.init()

    def _init_object_handler_without_db(self, params):
        """Initialize object handler without database connection."""
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=None, db_adapter=None)
        
        # Set cameras parameters from pipeline sources
        if hasattr(self.pipeline, "get_sources"):
            sources = self.pipeline.get_sources()
            if sources:
                cameras_params = []
                for source in sources:
                    if hasattr(source, 'source_ids') and hasattr(source, 'source_names') and source.source_ids and source.source_names:
                        camera_param = {
                            'source_ids': source.source_ids,
                            'source_names': source.source_names,
                            'camera': getattr(source, 'camera', '')
                        }
                        cameras_params.append(camera_param)
                
                # Set cameras params in obj_handler
                self.obj_handler.cameras_params = cameras_params
        
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
        self.preprocessors_proc = ProcessorFrame(class_name="PreprocessingPipeline", num_processors=num_preps, order=1)
        self.preprocessors_proc.set_params(params)
        self.preprocessors_proc.init()

    def _init_detectors(self, params):
        num_det = len(params)
        self.detectors_proc = ProcessorStep(class_name="ObjectDetectorYolo", num_processors=num_det, order=2)
        self.detectors_proc.set_params(params)
        self.detectors_proc.init()

    def _init_trackers(self, params):
        num_trackers = len(params)
        self.trackers_proc = ProcessorStep(class_name="ObjectTrackingBotsort", num_processors=num_trackers, order=3)
        self.trackers_proc.set_params(params)
        self.trackers_proc.init(encoders=self.encoders)

    def _init_mc_trackers(self, params):
        #num_of_cameras = len(self.params.get('sources', list()))
        self.mc_trackers_proc = ProcessorStep(class_name="ObjectMultiCameraTracking", num_processors=1, order=4)
        self.mc_trackers_proc.set_params(params)
        self.mc_trackers_proc.init(encoders=self.encoders)

        #self.mc_tracker = ObjectMultiCameraTracking(
        #    num_of_cameras,
        #    list(self.encoders.values())
        #)
        #self.mc_tracker.init()

    def _init_events_detectors(self, params):
        self.cam_events_detector = CamEventsDetector(self.pipeline.get_sources())
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
        self.zone_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector)
        for source in self.pipeline.get_sources():
            source.subscribe(self.cam_events_detector)

    def _init_events_detectors_without_db(self, params):
        """Initialize events detectors without database connection."""
        self.cam_events_detector = CamEventsDetector(self.pipeline.get_sources())
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        # Initialize FOV and Zone detectors without database functionality
        self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
        self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
        self.fov_events_detector.init()

        self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
        self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
        self.zone_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector)
        for source in self.pipeline.get_sources():
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

    def _init_events_processor_without_db(self, params):
        """Initialize events processor without database connection."""
        # Create dummy adapters that don't save to database
        self.events_processor = EventsProcessor([], None)  # No adapters, no db_controller
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
        # Calculate memory consumption for pipeline components
        self.pipeline.calc_memory_consumption()
        total_memory_usage += self.pipeline.memory_measure_results

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

        # Only collect database memory if database is enabled
        if self.use_database and self.db_controller:
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

    def _discover_pipeline_classes(self):
        """Discover all pipeline classes from packages and current directory"""
        pipeline_classes = {}
        
        # Search in evileye.pipelines package
        try:
            pipelines_module = importlib.import_module('evileye.pipelines')
            for name, obj in inspect.getmembers(pipelines_module):
                if (inspect.isclass(obj) and 
                    hasattr(obj, '__bases__') and 
                    any('Pipeline' in base.__name__ for base in obj.__bases__)):
                    pipeline_classes[name] = obj
        except ImportError as e:
            print(f"Warning: Could not import evileye.pipelines: {e}")
        
        # Search in current working directory pipelines folder
        current_dir = Path.cwd()
        pipelines_dir = current_dir / "pipelines"
        if pipelines_dir.exists() and pipelines_dir.is_dir():
            try:
                # Add current directory to Python path
                import sys
                sys.path.insert(0, str(current_dir))
                
                # Try to import pipelines module from current directory
                pipelines_module = importlib.import_module('pipelines')
                for name, obj in inspect.getmembers(pipelines_module):
                    if (inspect.isclass(obj) and 
                        hasattr(obj, '__bases__') and 
                        any('Pipeline' in base.__name__ for base in obj.__bases__)):
                        pipeline_classes[name] = obj
                
                # Remove from path
                sys.path.pop(0)
            except ImportError as e:
                print(f"Warning: Could not import local pipelines: {e}")
        
        return pipeline_classes
    
    def _create_pipeline_instance(self, pipeline_class_name: str):
        """Create pipeline instance by class name"""
        pipeline_classes = self._discover_pipeline_classes()
        
        if pipeline_class_name not in pipeline_classes:
            available_classes = list(pipeline_classes.keys())
            raise ValueError(f"Pipeline class '{pipeline_class_name}' not found. Available classes: {available_classes}")
        
        pipeline_class = pipeline_classes[pipeline_class_name]
        return pipeline_class()
    
    def get_available_pipeline_classes(self):
        """Get list of available pipeline classes"""
        return list(self._discover_pipeline_classes().keys())
    
    def create_config(self, num_sources: int, pipeline_class: str | None):
        """Create configuration with specified pipeline class"""
        self.init({})

        # Create pipeline instance if class name is provided
        if pipeline_class:
            try:
                self.pipeline = self._create_pipeline_instance(pipeline_class)
                print(f"Created pipeline instance: {pipeline_class}")
            except Exception as e:
                print(f"Warning: Could not create pipeline '{pipeline_class}': {e}")
                print("Falling back to default pipeline")
                self.pipeline = PipelineSurveillance()
        else:
            # Use default pipeline
            self.pipeline = PipelineSurveillance()

        if self.pipeline:
            self.pipeline.generate_default_structure(num_sources)

        config_data = {}
        self.update_params()
        
        # Get parameters safely, avoiding non-serializable objects
        config_data = self.get_params()

        config_data['visualizer'] = {}
        if num_sources and num_sources > 0:
            num_width = math.ceil(math.sqrt(num_sources))
            num_height = math.ceil(num_sources / num_width)

            config_data['visualizer']['num_width'] = num_width
            config_data['visualizer']['num_height'] = num_height
        else:
            config_data['visualizer']['num_width'] = 1
            config_data['visualizer']['num_height'] = 1

        config_data['visualizer']['visual_buffer_num_frames'] = 10
        if num_sources and num_sources > 0:
            config_data['visualizer']['source_ids'] = list(range(num_sources))
            config_data['visualizer']['fps'] = [5]*num_sources
        else:
            config_data['visualizer']['source_ids'] = []
            config_data['visualizer']['fps'] = []
        config_data['visualizer']['gui_enabled'] = False
        config_data['visualizer']['show_debug_info'] = True
        config_data['visualizer']['objects_journal_enabled'] = True

        self.stop()
        self.release()
        return config_data
    # def _save_video_duration(self):
    #     self.db_controller.update_video_dur(self.source_video_duration)
