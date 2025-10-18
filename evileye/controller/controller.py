import threading
import os
import importlib
import inspect
from pathlib import Path
from time import sleep

from evileye.capture import video_capture_opencv
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
from evileye.database_controller.db_adapter_system_events import DatabaseAdapterSystemEvents
from evileye.database_controller.db_adapter_attribute_events import DatabaseAdapterAttributeEvents
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_fov_events import JsonAdapterFovEvents
from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
from evileye.database_controller.json_adapter_cam_events import JsonAdapterCamEvents
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_system_events import JsonAdapterSystemEvents
from evileye.events_control.events_processor import EventsProcessor
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_detectors.cam_events_detector import CamEventsDetector
from evileye.events_detectors.fov_events_detector import FieldOfViewEventsDetector
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
from evileye.events_detectors.event_system import SystemEvent
from evileye.events_detectors.system_events_detector import SystemEventsDetector
import json
import datetime
import pprint
import copy
import math
from evileye.core import ProcessorSource, ProcessorStep, ProcessorFrame
from evileye.core.class_manager import ClassManager
from evileye.pipelines import PipelineSurveillance
from evileye.core.logger import get_module_logger


try:
    from PyQt6.QtWidgets import QMainWindow
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QMainWindow
    pyqt_version = 5

class Controller:
    def __init__(self):
        self.logger = get_module_logger("controller")
        self.main_window = None
        # self.application = application
        self.control_thread = threading.Thread(target=self.run)
        self.params = None
        self.loaded_config = dict()
        self.credentials = dict()
        self.credentials_loaded = False
        self.params_path = None
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
        self.memory_periodic_check_sec = 60*15*60
        self.max_memory_usage_mb = 1024*16
        self.show_memory_usage = False
        self.auto_restart = True
        self.use_database = True  # Default to True for backward compatibility
        # Timeout for late model loading/class mapping propagation (seconds)
        self.model_loading_timeout_sec = 60

        self.events_detectors_controller = None
        self.events_processor = None
        self.cam_events_detector = None
        self.fov_events_detector = None
        self.zone_events_detector = None
        self.attr_events_detector = None
        self.system_events_detector = None

        self.db_controller = None
        self.db_adapter_obj = None
        self.db_adapter_cam_events = None
        self.db_adapter_fov_events = None
        self.db_adapter_zone_events = None
        self.db_adapter_attr_events = None
        self.db_adapter_system_events = None
        
        # Initialize centralized class manager
        self.class_manager = ClassManager()
        
        # Default COCO class mapping: class_name -> class_id
        self.class_mapping = {
            "person": 0,
            "bicycle": 1,
            "car": 2,
            "motorcycle": 3,
            "airplane": 4,
            "bus": 5,
            "train": 6,
            "truck": 7,
            "boat": 8,
            "traffic light": 9,
            "fire hydrant": 10,
            "stop sign": 11,
            "parking meter": 12,
            "bench": 13,
            "bird": 14,
            "cat": 15,
            "dog": 16,
            "horse": 17,
            "sheep": 18,
            "cow": 19,
            "elephant": 20,
            "bear": 21,
            "zebra": 22,
            "giraffe": 23,
            "backpack": 24,
            "umbrella": 25,
            "handbag": 26,
            "tie": 27,
            "suitcase": 28,
            "frisbee": 29,
            "skis": 30,
            "snowboard": 31,
            "sports ball": 32,
            "kite": 33,
            "baseball bat": 34,
            "baseball glove": 35,
            "skateboard": 36,
            "surfboard": 37,
            "tennis racket": 38,
            "bottle": 39,
            "wine glass": 40,
            "cup": 41,
            "fork": 42,
            "knife": 43,
            "spoon": 44,
            "bowl": 45,
            "banana": 46,
            "apple": 47,
            "sandwich": 48,
            "orange": 49,
            "broccoli": 50,
            "carrot": 51,
            "hot dog": 52,
            "pizza": 53,
            "donut": 54,
            "cake": 55,
            "chair": 56,
            "couch": 57,
            "potted plant": 58,
            "bed": 59,
            "dining table": 60,
            "toilet": 61,
            "tv": 62,
            "laptop": 63,
            "mouse": 64,
            "remote": 65,
            "keyboard": 66,
            "cell phone": 67,
            "microwave": 68,
            "oven": 69,
            "toaster": 70,
            "sink": 71,
            "refrigerator": 72,
            "book": 73,
            "clock": 74,
            "vase": 75,
            "scissors": 76,
            "teddy bear": 77,
            "hair drier": 78,
            "toothbrush": 79
        }

        self.run_flag = False
        self.restart_flag = False

        self.gui_enabled = True
        self.autoclose = False
        #self.multicam_reid_enabled = False

        self.current_main_widget_size = [1920, 1080]

        self.debug_info = dict()

    def get_fps(self) -> int:
        return self.fps

    def get_params(self):
        return self.params

    def system_event(self, type: str, message: str):
        if self.system_events_detector:
            self.system_events_detector.emit_message(type, message)

        self.logger.info(f"System message [{type}]: {message}")

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
        # Emit system started via detector (unified path)
        if self.system_events_detector:
            self.system_events_detector.emit_started()
        while self.run_flag:
            begin_it = timer()
            # Process pipeline: sources -> preprocessors -> detectors -> trackers -> mc_trackers
            self.pipeline.process()
            all_sources_finished = self.pipeline.check_all_sources_finished()

            pipeline_results = self.pipeline.peek_latest_result()

            #mc_tracking_results = pipeline_results.get("mc_trackers", [])
            if self.pipeline is not None and pipeline_results is not None:
                mc_tracking_results = pipeline_results.get(self.pipeline.get_final_results_name(), [])
            else:
                mc_tracking_results = []

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
                # Handle both tuples [tracking_result, image] and Frame objects
                if isinstance(track_info, (tuple, list)) and len(track_info) == 2:
                    tracking_result, image = track_info
                else:
                    # Assume it's a Frame object (from attributes processors)
                    tracking_result = None
                    image = track_info
                
                self.obj_handler.put(track_info)
                processing_frames.append(image)
                self.source_last_processed_frame_id[image.source_id] = image.frame_id

            events = dict()
            events = self.events_detectors_controller.get()
            # self.logger.debug(f"Events: {events}")
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
                        self.logger.warning(f"Memory usage exceeded: {total_memory_usage_mb:.2f} Mb (maximum: {self.max_memory_usage_mb:.2f} Mb)")
                        self.logger.debug(f"Debug info: {pprint.pformat(self.debug_info)}")
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

            #self.logger.debug(f"Time: cap[{complete_capture_it-begin_it}], det[{complete_detection_it-complete_capture_it}], track[{complete_tracking_it-complete_detection_it}], events[{complete_processing_it-complete_tracking_it}]], "
            #       f"read=[{complete_read_objects_it-complete_processing_it}], vis[{end_it-complete_read_objects_it}] = {end_it-begin_it} secs, sleep {sleep_seconds} secs")
            time.sleep(sleep_seconds)

        if self.system_events_detector:
            self.system_events_detector.emit_stopped()
            time.sleep(0.2)

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
                if self.db_adapter_attr_events:
                    self.db_adapter_attr_events.start()
                if self.db_adapter_system_events:
                    self.db_adapter_system_events.start()
            except Exception as e:
                self.logger.warning(f"Database connection error at startup. Disabling database functionality. Reason: {e}")
                self.use_database = False
                self.db_controller = None
        
        self.zone_events_detector.start()
        self.cam_events_detector.start()
        self.fov_events_detector.start()
        if self.attr_events_detector:
            self.attr_events_detector.start()
        if self.system_events_detector:
            self.system_events_detector.start()
        self.events_detectors_controller.start()
        self.events_processor.start()

        self.run_flag = True
        self.control_thread.start()

    def stop(self):
        # self._save_video_duration()

        self.run_flag = False
        if self.control_thread.is_alive():
            self.control_thread.join()
        if self.visualizer:
            self.visualizer.stop()
        self.obj_handler.stop()

        self.cam_events_detector.stop()
        self.fov_events_detector.stop()
        self.zone_events_detector.stop()
        if self.attr_events_detector:
            self.attr_events_detector.stop()
        if self.system_events_detector:
            self.system_events_detector.stop()
        # Flush events controller once before stopping and forward to processor
        self.events_detectors_controller.flush_once()
        events = self.events_detectors_controller.get()
        if events:
            self.events_processor.put(events)
        self.events_detectors_controller.stop()
        self.events_processor.stop()

        # Stop database components only if database is enabled
        if self.use_database and self.db_controller:
            self.db_adapter_cam_events.stop()
            self.db_adapter_fov_events.stop()
            self.db_adapter_zone_events.stop()
            if self.db_adapter_attr_events:
                self.db_adapter_attr_events.stop()
            if self.db_adapter_system_events:
                self.db_adapter_system_events.stop()
            self.db_adapter_obj.stop()
            self.db_controller.disconnect()
        
        # Stop pipeline components
        self.pipeline.stop()
        self.logger.info('All controller components stopped')

    def init(self, params):
        self.params = params
        # Сохраняем исходный конфиг для правил частичного сохранения
        try:
            import copy as _copy
            self.loaded_config = _copy.deepcopy(params) if isinstance(params, dict) else dict()
        except Exception:
            self.loaded_config = dict()

        if 'controller' in self.params.keys():
            self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
            self.fps = self.params['controller'].get("fps", self.fps)
            self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
            self.gui_enabled = self.params['controller'].get("gui_enabled", self.gui_enabled)

            self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
            self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
            # Handle both old class_names format and new class_mapping format
            if "class_mapping" in self.params['controller']:
                self.class_mapping = self.params['controller'].get("class_mapping", {})
            elif "class_names" in self.params['controller']:
                # Convert old class_names list to class_mapping dict
                class_names = self.params['controller'].get("class_names", [])
                self.class_mapping = {name: idx for idx, name in enumerate(class_names)}
            else:
                # Keep default class_mapping if neither is specified
                pass
            # Optional: override late model loading timeout
            self.model_loading_timeout_sec = self.params['controller'].get("model_loading_timeout_sec", self.model_loading_timeout_sec)
            self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
            self.show_memory_usage = self.params['controller'].get("show_memory_usage", self.show_memory_usage)
            self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
            self.auto_restart = self.params['controller'].get("auto_restart", self.auto_restart)
            self.use_database = self.params['controller'].get("use_database", self.use_database)

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
                self.credentials_loaded = True
        except FileNotFoundError as ex:
            self.credentials_loaded = False

        # Initialize processing pipeline (sources, preprocessors, detectors, trackers)
        pipeline_params = self.params.get("pipeline", {})
        pipeline_class_name = pipeline_params.get("pipeline_class")
        
        if pipeline_class_name:
            try:
                self.pipeline = self._create_pipeline_instance(pipeline_class_name)
                self.logger.info(f"Using pipeline class: {pipeline_class_name}")
            except Exception as e:
                self.logger.warning(f"Failed to create pipeline '{pipeline_class_name}': {e}")
                self.logger.info("Using default PipelineSurveillance")
                self.pipeline = PipelineSurveillance()
        else:
            self.logger.warning("Pipeline class not specified in parameters, using default PipelineSurveillance")
            self.pipeline = PipelineSurveillance()
        
        self.pipeline.set_credentials(self.credentials)
        self.pipeline.set_params(**pipeline_params)
        self.pipeline.init()
        
        # Preload controller's class mapping into centralized ClassManager
        # This allows detectors to convert class names to IDs immediately if provided
        try:
            if self.class_mapping:
                self.class_manager.add_class_mapping(self.class_mapping, 'controller_default')
        except Exception:
            pass

        # Set ClassManager for all detectors ASAP (before class mapping update)
        try:
            if hasattr(self.pipeline, 'processors'):
                for processor in self.pipeline.processors:
                    if hasattr(processor, 'get_processors'):
                        for proc in processor.get_processors():
                            if hasattr(proc, 'set_class_manager'):
                                proc.set_class_manager(self.class_manager)
        except Exception:
            pass

        # Update class_mapping from detectors after pipeline initialization
        self.update_class_mapping_from_detectors()

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
                self._init_object_handler(self.db_controller, params.get('objects_handler') or dict())
                self._init_events_detectors(self.params.get('events_detectors', dict()))
                self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
                self._init_events_processor(self.params.get('events_processor', dict()))
            except Exception as e:
                self.logger.warning(f"Database enabled but unavailable. Working without database. Reason: {e}")
                # Fallback to no-database mode
                self.use_database = False
                self.db_controller = None
                self.database_config = {"database": {}, "database_adapters": {}}
                self._init_object_handler_without_db(params.get('objects_handler') or dict())
                self._init_events_detectors_without_db(self.params.get('events_detectors', dict()))
                self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
                self._init_events_processor_without_db(self.params.get('events_processor', dict()))
        else:
            self.logger.info("Database functionality disabled. Working without database connection.")
            # Initialize minimal components for operation without database
            self._init_object_handler_without_db(params.get('objects_handler') or dict())
            self._init_events_detectors_without_db(self.params.get('events_detectors', dict()))
            self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
            self._init_events_processor_without_db(self.params.get('events_processor', dict()))

    def init_main_window(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self._init_visualizer(self.params.get('visualizer', dict()))

    def release(self):
        self.stop()
        # Release pipeline components
        self.pipeline.release()
        self.logger.info('All controller components released')

    def update_params(self):
        self.params['controller'] = dict()
        self.params['controller']["autoclose"] = self.autoclose
        self.params['controller']["fps"] = self.fps
        self.params['controller']["show_main_gui"] = self.show_main_gui
        self.params['controller']["gui_enabled"] = self.gui_enabled
        self.params['controller']["show_journal"] = self.show_journal
        self.params['controller']["enable_close_from_gui"] = self.enable_close_from_gui
        # Сохраняем class_mapping только если он присутствовал в исходной конфигурации
        try:
            orig_ctrl = (self.loaded_config or {}).get('controller', {})
            had_class_mapping = isinstance(orig_ctrl, dict) and (('class_mapping' in orig_ctrl) or ('class_names' in orig_ctrl))
        except Exception:
            had_class_mapping = True
        if had_class_mapping:
            self.params['controller']["class_mapping"] = self.class_mapping
        self.params['controller']["memory_periodic_check_sec"] = self.memory_periodic_check_sec
        self.params['controller']["show_memory_usage"] = self.show_memory_usage

        self.params['controller']["max_memory_usage_mb"] = self.max_memory_usage_mb
        self.params['controller']["auto_restart"] = self.auto_restart
        self.params['controller']["use_database"] = self.use_database

        # Get pipeline parameters
        pipeline_params = self.pipeline.get_params()
        self.params['pipeline'] = pipeline_params

        # Очистка корня параметров от секций пайплайна (не дублируем их вне 'pipeline')
        try:
            pipeline_section_names = [
                'sources', 'preprocessors', 'detectors', 'trackers', 'mc_trackers',
                'attributes_roi', 'attributes_classifier'
            ]
            for key in pipeline_section_names:
                if key in self.params:
                    try:
                        del self.params[key]
                    except Exception:
                        pass
        except Exception:
            pass

        # Collect objects_handler params with safe fallback to existing/loaded config
        try:
            if self.obj_handler:
                oh_params = self.obj_handler.get_params()
            else:
                oh_params = None
        except Exception:
            oh_params = None
        if not isinstance(oh_params, dict) or not oh_params:
            # Fallback to previously stored or originally loaded config
            oh_params = (self.params.get('objects_handler') if isinstance(self.params, dict) else None) or \
                        ((self.loaded_config or {}).get('objects_handler') if isinstance(self.loaded_config, dict) else None) or {}
        self.params['objects_handler'] = oh_params

        self.params['events_detectors'] = dict()
        self.params['events_detectors']['CamEventsDetector'] = self.cam_events_detector.get_params()
        self.params['events_detectors']['FieldOfViewEventsDetector'] = self.fov_events_detector.get_params()
        self.params['events_detectors']['ZoneEventsDetector'] = self.zone_events_detector.get_params()
        if self.attr_events_detector:
            self.params['events_detectors']['AttributeEventsDetector'] = self.attr_events_detector.get_params()

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

        # Collect visualizer params with safe fallback
        vis_params = None
        try:
            if self.visualizer:
                vis_params = self.visualizer.get_params()
        except Exception:
            vis_params = None
        if not isinstance(vis_params, dict) or not vis_params:
            vis_params = (self.params.get('visualizer') if isinstance(self.params, dict) else None) or \
                         ((self.loaded_config or {}).get('visualizer') if isinstance(self.loaded_config, dict) else None) or {}
        self.params['visualizer'] = vis_params

        # Text configuration is now part of visualizer section
        # No need to add separate text_config here

        # Дополнительная защита: сразу после обновления параметров удаляем чувствительные поля,
        # model_class_mapping и ограничиваем секцию database ключами исходной конфигурации
        try:
            self._reconcile_credentials_fields(self.params, self.loaded_config, self.credentials_loaded)
        except Exception:
            pass
        try:
            self._filter_model_class_mapping(self.params, self.loaded_config)
        except Exception:
            pass
        try:
            if isinstance(self.loaded_config, dict) and self.loaded_config:
                self._restrict_database_keys(self.params, self.loaded_config)
        except Exception:
            pass

    def _atomic_json_dump(self, path: str, data: dict) -> bool:
        try:
            if not path:
                self.logger.error("No config file path specified for saving")
                return False
            import tempfile
            dir_name = os.path.dirname(path) or "."
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=dir_name, prefix=".tmp_") as tf:
                json.dump(data, tf, indent=4, ensure_ascii=False)
                temp_path = tf.name
            os.replace(temp_path, path)
            return True
        except Exception as e:
            try:
                self.logger.error(f"Failed to save configuration atomically: {e}")
            except Exception:
                pass
            return False

    def _restrict_database_keys(self, params: dict, loaded_config: dict) -> None:
        try:
            orig_db = (loaded_config or {}).get('database', {}) or {}
            if not isinstance(orig_db, dict):
                return
            current_db = params.get('database', {}) or {}
            if not isinstance(current_db, dict):
                params['database'] = {}
                return
            allowed_keys = set(orig_db.keys())
            params['database'] = {k: current_db[k] for k in current_db.keys() if k in allowed_keys}
        except Exception:
            # В случае ошибки не модифицируем секцию
            pass

    def _reconcile_credentials_fields(self, params: dict, loaded_config: dict, credentials_loaded: bool) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            sources = pipeline.get('sources', []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return

            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_sources = orig_pipeline.get('sources', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_sources = []

            CRED_KEYS = {
                'user_name', 'username', 'password', 'pwd', 'login', 'token',
                'rtsp_user', 'rtsp_password', 'auth', 'api_key', 'camera_login', 'camera_password'
            }

            def _strip_userinfo_from_url(url: str) -> str:
                try:
                    from urllib.parse import urlsplit, urlunsplit
                    parts = urlsplit(url)
                    netloc = parts.netloc
                    if '@' in netloc:
                        # remove userinfo
                        hostport = netloc.split('@', 1)[1]
                        new_parts = (parts.scheme, hostport, parts.path, parts.query, parts.fragment)
                        return urlunsplit(new_parts)
                    return url
                except Exception:
                    return url

            def _has_userinfo(url: str) -> bool:
                try:
                    from urllib.parse import urlsplit
                    parts = urlsplit(url)
                    return ('@' in parts.netloc)
                except Exception:
                    return ('@' in (url or ''))

            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = orig_sources[idx] if idx < len(orig_sources) and isinstance(orig_sources[idx], dict) else {}
                orig_cred_keys = {k for k in (orig_src.keys() if isinstance(orig_src, dict) else []) if k in CRED_KEYS}
                keys_to_remove = set()
                for k in list(src.keys()):
                    if k in CRED_KEYS and k not in orig_cred_keys:
                        keys_to_remove.add(k)
                for k in keys_to_remove:
                    try:
                        del src[k]
                    except Exception:
                        pass

                # Additionally: handle embedded credentials in camera URL
                try:
                    cam_now = src.get('camera')
                    cam_orig = orig_src.get('camera') if isinstance(orig_src, dict) else None
                    if isinstance(cam_now, str):
                        # If original didn't have userinfo in URL, strip userinfo from current
                        if not isinstance(cam_orig, str) or not _has_userinfo(cam_orig):
                            src['camera'] = _strip_userinfo_from_url(cam_now)
                        else:
                            # original had userinfo -> keep presence allowed; do not alter
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_api_preference(self, params: dict, loaded_config: dict) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            sources = pipeline.get('sources', []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return
            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_sources = orig_pipeline.get('sources', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_sources = []
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = orig_sources[idx] if idx < len(orig_sources) and isinstance(orig_sources[idx], dict) else {}
                if isinstance(orig_src, dict) and ('apiPreference' in orig_src):
                    src['apiPreference'] = orig_src.get('apiPreference')
        except Exception:
            pass

    def _filter_model_class_mapping(self, params: dict, loaded_config: dict) -> None:
        try:
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            detectors = pipeline.get('detectors', []) if isinstance(pipeline, dict) else []
            if not isinstance(detectors, list) or not detectors:
                return
            try:
                orig_pipeline = (loaded_config or {}).get('pipeline', {})
                orig_detectors = orig_pipeline.get('detectors', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_detectors = []
            for idx, det in enumerate(detectors):
                if not isinstance(det, dict):
                    continue
                orig_det = orig_detectors[idx] if idx < len(orig_detectors) and isinstance(orig_detectors[idx], dict) else {}
                if 'model_class_mapping' in det and ('model_class_mapping' not in orig_det):
                    try:
                        del det['model_class_mapping']
                    except Exception:
                        pass
        except Exception:
            pass

    def save_config(self, file_path: str | None = None) -> bool:
        try:
            self.update_params()
        except Exception:
            pass

        try:
            import copy as _copy
            final_params = _copy.deepcopy(self.params) if isinstance(self.params, dict) else {}
        except Exception:
            final_params = self.params if isinstance(self.params, dict) else {}

        try:
            self._reconcile_credentials_fields(final_params, self.loaded_config, self.credentials_loaded)
        except Exception:
            pass

        try:
            if isinstance(self.loaded_config, dict) and self.loaded_config:
                self._restrict_database_keys(final_params, self.loaded_config)
        except Exception:
            pass

        # Отфильтровать model_class_mapping перед записью
        try:
            self._filter_model_class_mapping(final_params, self.loaded_config)
        except Exception:
            pass

        # Финальная защита: убрать любые секции пайплайна с корня перед записью
        try:
            pipe_keys = [
                'sources', 'preprocessors', 'detectors', 'trackers', 'mc_trackers',
                'attributes_roi', 'attributes_classifier'
            ]
            for k in pipe_keys:
                if k in final_params:
                    try:
                        del final_params[k]
                    except Exception:
                        pass
        except Exception:
            pass

        path = file_path or getattr(self, 'params_path', None)
        ok = self._atomic_json_dump(path, final_params)
        if ok:
            try:
                self.logger.info(f"Configuration saved by controller to: {path}")
            except Exception:
                pass

        if ok and self.use_database and hasattr(self, 'db_controller') and self.db_controller:
            try:
                self.db_controller.save_job_configuration_info(final_params)
            except Exception as e:
                try:
                    self.logger.warning(f"Failed to update job config in DB: {e}")
                except Exception:
                    pass
        return ok

    def set_current_main_widget_size(self, width, height):
        self.current_main_widget_size = [width, height]
        self.visualizer.set_current_main_widget_size(width, height)

    def _init_object_handler(self, db_controller, params):
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=db_controller, db_adapter=self.db_adapter_obj)
        safe_params = params or {}
        self.obj_handler.set_params(**safe_params)
        # Set class manager for ObjectsHandler
        if hasattr(self.obj_handler, 'class_manager'):
            self.obj_handler.class_manager = self.class_manager
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
        
        safe_params = params or {}
        self.obj_handler.set_params(**safe_params)
        # Set class manager for ObjectsHandler
        if hasattr(self.obj_handler, 'class_manager'):
            self.obj_handler.class_manager = self.class_manager
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

        self.db_adapter_attr_events = DatabaseAdapterAttributeEvents(self.db_controller)
        self.db_adapter_attr_events.set_params(**params['DatabaseAdapterAttributeEvents'])
        self.db_adapter_attr_events.init()

        self.db_adapter_system_events = DatabaseAdapterSystemEvents(self.db_controller)
        self.db_adapter_system_events.set_params(**params['DatabaseAdapterSystemEvents'])
        self.db_adapter_system_events.init()

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

        # Initialize AttributeEventsDetector
        self.attr_events_detector = AttributeEventsDetector(self.obj_handler)
        self.attr_events_detector.set_params(**params.get('AttributeEventsDetector', dict()))
        self.attr_events_detector.init()

        # Initialize SystemEventsDetector
        self.system_events_detector = SystemEventsDetector()
        self.system_events_detector.set_params(**params.get('SystemEventsDetector', dict()))
        self.system_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector, self.attr_events_detector)
        for source in self.pipeline.get_sources():
            source.subscribe(self.cam_events_detector)
        
        # Инициализация атрибутных процессоров, если они есть в пайплайне
        self._init_attributes_processors(params)

    def _init_attributes_processors(self, params):
        """Инициализация атрибутных процессоров и связывание с ObjectsHandler."""
        # Проверяем, есть ли атрибутные процессоры в пайплайне
        if hasattr(self.pipeline, 'processors'):
            for processor in self.pipeline.processors:
                if hasattr(processor, 'get_name'):
                    proc_name = processor.get_name()
                    if proc_name in ['attributes_roi', 'attributes_classifier']:
                        # Получаем параметры для атрибутных процессоров
                        attr_params = params.get('attributes_detection', {})
                        if attr_params:
                            # Прокидываем параметры в ObjectsHandler
                            if 'objects_handler' not in self.obj_handler.params:
                                self.obj_handler.params['objects_handler'] = {}
                            self.obj_handler.params['objects_handler']['attributes_detection'] = attr_params
                            self.obj_handler.set_params_impl()
                            self.logger.info(f"Attribute detection configured for {proc_name}")

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

        # Initialize AttributeEventsDetector
        self.attr_events_detector = AttributeEventsDetector(self.obj_handler)
        self.attr_events_detector.set_params(**params.get('AttributeEventsDetector', dict()))
        self.attr_events_detector.init()

        # Initialize SystemEventsDetector
        self.system_events_detector = SystemEventsDetector()
        self.system_events_detector.set_params(**params.get('SystemEventsDetector', dict()))
        self.system_events_detector.init()

        self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector, self.attr_events_detector)
        for source in self.pipeline.get_sources():
            source.subscribe(self.cam_events_detector)

    def _init_events_detectors_controller(self, params):
        detectors = [self.cam_events_detector, self.fov_events_detector, self.zone_events_detector]
        if self.attr_events_detector:
            detectors.append(self.attr_events_detector)
        if self.system_events_detector:
            detectors.append(self.system_events_detector)
        self.events_detectors_controller = EventsDetectorsController(detectors)
        self.events_detectors_controller.set_params(**params)
        self.events_detectors_controller.init()

    def _init_events_processor(self, params):
        # Backward-compatible: delegate to unified initializer
        self._init_events_processor_unified(params)

    def _init_events_processor_without_db(self, params):
        """Initialize events processor without database connection."""
        # Backward-compatible: delegate to unified initializer
        self._init_events_processor_unified(params)

    def _get_event_adapters(self):
        """Build list of event adapters depending on database mode."""
        if self.use_database and self.db_controller:
            adapters = [self.db_adapter_fov_events, self.db_adapter_cam_events, self.db_adapter_zone_events]
            if self.db_adapter_attr_events:
                adapters.append(self.db_adapter_attr_events)
            if self.db_adapter_system_events:
                adapters.append(self.db_adapter_system_events)
            try:
                self.logger.info(f"DB adapters: {[a.get_event_name() for a in adapters if a]}")
            except Exception:
                pass
            return adapters
        # JSON adapters when DB disabled or unavailable
        adapters = []
        img_dir = self.params.get('database', {}).get('image_dir', 'EvilEyeData')
        for adapter_cls in (JsonAdapterAttributeEvents, JsonAdapterFovEvents, JsonAdapterZoneEvents, JsonAdapterCamEvents, JsonAdapterSystemEvents):
            try:
                adapter = adapter_cls(None)
                adapter.set_params(image_dir=img_dir)
                adapter.init()
                adapter.start()
                adapters.append(adapter)
                try:
                    self.logger.info(f"JSON adapter started: {adapter.get_event_name()} -> image_dir={img_dir}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.logger.error(f"Failed to start JSON adapter {adapter_cls.__name__}: {e}")
                except Exception:
                    pass
        return adapters

    def _init_events_processor_unified(self, params):
        """Unified initializer for EventsProcessor for both DB and JSON modes."""
        adapters = self._get_event_adapters()
        db_ctrl = self.db_controller if (self.use_database and self.db_controller) else None
        self.events_processor = EventsProcessor(adapters, db_ctrl)
        self.events_processor.set_params(**params)
        self.events_processor.init()
        # Wire UI callback for online signalization
        try:
            self.events_processor.set_ui_callback(self._on_event_signalization)
        except Exception:
            pass

    def _on_event_signalization(self, source_id: int, object_id: int, event_name: str, is_on: bool, bbox_px: list | None = None):
        """Relay event signalization to main window (per source)."""
        try:
            # Diagnostics logging removed
            # Route directly via visualizer
            if self.visualizer and hasattr(self.visualizer, 'set_event_state'):
                self.visualizer.set_event_state(source_id, object_id, event_name, is_on, bbox_px)
        except Exception:
            pass

    def _init_visualizer(self, params):
        self.visualizer = Visualizer(self.pyqt_slots, self.pyqt_signals)
        self.visualizer.set_params(**params)
        self.visualizer.source_id_name_table = self.source_id_name_table
        self.visualizer.source_video_duration = self.source_video_duration
        self.visualizer.class_mapping = self.class_mapping  # Pass class mapping to visualizer
        self.visualizer.init()
        # If persistent zones display requested, push existing zones to threads immediately
        try:
            vis_wants_zones = bool(self.visualizer.get_params().get('display_zones', False))
        except Exception:
            vis_wants_zones = False
        if vis_wants_zones:
            try:
                zones_cfg = (((self.params or {}).get('events_detectors', {}) or {}).get('ZoneEventsDetector', {}) or {}).get('sources', {})
                sources_zones = {}
                if isinstance(zones_cfg, dict):
                    for k, zone_list in zones_cfg.items():
                        try:
                            sid = int(k)
                        except Exception:
                            continue
                        sources_zones[sid] = []
                        for coords in (zone_list or []):
                            # expected: ['poly', coords, None]
                            if isinstance(coords, list) and coords:
                                sources_zones[sid].append(['poly', coords, None])
                if sources_zones:
                    try:
                        self.pyqt_signals['display_zones_signal'].emit(sources_zones)
                    except Exception:
                        pass
            except Exception:
                pass

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
            self.logger.warning(f"Failed to import evileye.pipelines: {e}")
        
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
                self.logger.warning(f"Failed to import local pipelines: {e}")
        
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
    
    def get_class_name(self, class_id: int) -> str:
        """Get class name from class ID using class_mapping"""
        for name, cid in self.class_mapping.items():
            if cid == class_id:
                return name
        return f"class_{class_id}"
    
    def get_class_id(self, class_name: str) -> int:
        """Get class ID from class name using class_mapping"""
        return self.class_mapping.get(class_name, -1)
    
    def get_class_names_list(self) -> list:
        """Get list of class names in order of their IDs"""
        sorted_classes = sorted(self.class_mapping.items(), key=lambda x: x[1])
        return [name for name, _ in sorted_classes]
    
    def update_class_mapping_from_detectors(self):
        """Update class_mapping from all detectors in the pipeline using ClassManager"""
        if not hasattr(self, 'pipeline') or not self.pipeline:
            return
            
        # Get all detectors from pipeline
        detectors = []
        if hasattr(self.pipeline, 'processors'):
            for processor in self.pipeline.processors:
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        if hasattr(proc, 'get_model_class_mapping'):
                            detectors.append(proc)
        
        # Collect class mappings from all detectors using ClassManager
        for detector in detectors:
            mapping = detector.get_model_class_mapping()
            if mapping:
                detector_name = detector.__class__.__name__
                success = self.class_manager.add_class_mapping(mapping, detector_name)
                if not success:
                    self.logger.warning(f"Conflicts detected when adding mapping from {detector_name}")
                
                # CRITICAL: Force update classes after getting model mapping
                if hasattr(detector, '_update_classes_after_model_loading'):
                    detector._update_classes_after_model_loading()
            else:
                # Model not loaded yet, try to get mapping (this will trigger late update if model is loaded)
                detector.get_model_class_mapping()
        
        # Update controller's class_mapping from ClassManager
        if self.class_manager.class_mapping:
            self.class_mapping = self.class_manager.get_class_mapping()
            self.logger.info(f"Updated controller class_mapping with {len(self.class_mapping)} classes from {len(detectors)} detectors")
            
            # Update visualizer if available
            if hasattr(self, 'visualizer') and self.visualizer:
                self.visualizer.class_mapping = self.class_mapping
                self.logger.info("Updated visualizer class_mapping")
            
            # Set class manager for all detectors
            for detector in detectors:
                if hasattr(detector, 'set_class_manager'):
                    detector.set_class_manager(self.class_manager)
            
            # Report conflicts if any
            if self.class_manager.has_conflicts():
                self.logger.warning("Class mapping conflicts detected:")
                for conflict in self.class_manager.get_conflicts():
                    self.logger.warning(f"   - {conflict}")
                self.logger.info("Using first occurrence for each class name/ID pair.")
        else:
            self.logger.warning("Class mappings not found in detectors")
            
        # Schedule periodic check for late model loading
        self._schedule_periodic_class_update()
    
    def _schedule_periodic_class_update(self):
        """Schedule periodic check for classes update after model loading"""
        import threading
        import time
        
        def periodic_check():
            """Periodically check and update classes"""
            # Check once per second up to configured timeout
            max_attempts = max(1, int(self.model_loading_timeout_sec))
            attempt = 0
            
            while attempt < max_attempts:
                time.sleep(1)  # Wait 1 second
                attempt += 1
                
                # Check if we have detectors
                if not hasattr(self, 'pipeline') or not self.pipeline:
                    continue
                    
                # Get all detectors from pipeline
                detectors = []
                if hasattr(self.pipeline, 'processors'):
                    for processor in self.pipeline.processors:
                        if hasattr(processor, 'get_processors'):
                            for proc in processor.get_processors():
                                if hasattr(proc, 'get_model_class_mapping'):
                                    detectors.append(proc)
                
                # Check each detector
                updated = False
                for detector in detectors:
                    mapping = detector.get_model_class_mapping()
                    if mapping and hasattr(detector, '_check_and_update_classes_if_needed'):
                        detector._check_and_update_classes_if_needed()
                        updated = True
                
                if updated:
                    self.logger.info("Late model loading detected, classes updated")
                    break
                    
            if attempt >= max_attempts:
                self.logger.warning("Model loading timeout, some classes may not update")
        
        # Start periodic check in background thread
        check_thread = threading.Thread(target=periodic_check, daemon=True)
        check_thread.start()
    
    def create_config(self, num_sources: int, pipeline_class: str | None, 
                     source_type: str = 'video_file', detector_params: dict | None = None,
                     tracker_params: dict | None = None, database_params: dict | None = None):
        """Create configuration with specified pipeline class and optional parameters"""
        self.init({})

        # Create pipeline instance if class name is provided
        if pipeline_class:
            try:
                self.pipeline = self._create_pipeline_instance(pipeline_class)
                self.logger.info(f"Created pipeline instance: {pipeline_class}")
            except Exception as e:
                self.logger.warning(f"Failed to create pipeline '{pipeline_class}': {e}")
                self.logger.info("Using default pipeline")
                self.pipeline = PipelineSurveillance()
        else:
            # Use default pipeline
            self.pipeline = PipelineSurveillance()

        if self.pipeline:
            self.pipeline.generate_default_structure(num_sources)

        # Apply source type configuration
        if num_sources > 0 and hasattr(self.pipeline, 'sources') and self.pipeline.sources:
            source_type_mapping = {
                'video_file': {'source': 'video_file', 'camera': 'path/to/video.mp4'},
                'ip_camera': {'source': 'ip_camera', 'camera': 'rtsp://user:password@ip:port/stream'},
                'device': {'source': 'device', 'camera': 0}
            }
            
            if source_type in source_type_mapping:
                source_config = source_type_mapping[source_type]
                for source in self.pipeline.sources:
                    if hasattr(source, 'source') and hasattr(source, 'camera'):
                        source.source = source_config['source']
                        source.camera = source_config['camera']
                        self.logger.info(f"Applied source type '{source_type}' to source")

        # Apply detector parameters if provided
        if detector_params and hasattr(self.pipeline, 'processors'):
            for processor in self.pipeline.processors:
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        if hasattr(proc, 'get_name') and 'detector' in proc.get_name().lower():
                            try:
                                proc.set_params(**detector_params)
                                self.logger.info(f"Applied detector parameters: {detector_params}")
                            except Exception as e:
                                self.logger.warning(f"Failed to apply detector parameters: {e}")

        # Apply tracker parameters if provided
        if tracker_params and hasattr(self.pipeline, 'processors'):
            for processor in self.pipeline.processors:
                if hasattr(processor, 'get_processors'):
                    for proc in processor.get_processors():
                        if hasattr(proc, 'get_name') and 'tracker' in proc.get_name().lower():
                            try:
                                proc.set_params(**tracker_params)
                                self.logger.info(f"Applied tracker parameters: {tracker_params}")
                            except Exception as e:
                                self.logger.warning(f"Failed to apply tracker parameters: {e}")

        config_data = {}
        self.update_params()
        
        # Get parameters safely, avoiding non-serializable objects
        config_data = self.get_params()

        # Apply database parameters (only safe parameters, no credentials)
        if database_params:
            # Only store safe database parameters (no credentials)
            safe_db_params = {}
            safe_keys = ['image_dir', 'preview_width', 'preview_height']
            for key in safe_keys:
                if key in database_params:
                    safe_db_params[key] = database_params[key]
            
            # Set default safe values if not provided
            if not safe_db_params:
                safe_db_params = {
                    "image_dir": "EvilEyeData",
                    "preview_width": 300,
                    "preview_height": 150
                }
            
            # Replace entire database section with only safe parameters
            config_data['database'] = safe_db_params
            self.logger.info(f"Applied safe database parameters: {safe_db_params}")
        else:
            # If no database_params provided, ensure database section contains only safe parameters
            if 'database' in config_data:
                # Keep only safe parameters, remove credentials
                safe_db_params = {
                    "image_dir": "EvilEyeData",
                    "preview_width": 300,
                    "preview_height": 150
                }
                config_data['database'] = safe_db_params
                self.logger.info(f"Removed database credentials, kept only safe parameters: {safe_db_params}")

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
