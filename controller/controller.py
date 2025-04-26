import threading
import capture
from object_detector import object_detection_yolo
from object_detector.object_detection_base import DetectionResultList
from object_tracker import object_tracking_botsort
from object_tracker.object_tracking_base import TrackingResultList
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
from PyQt6.QtWidgets import QMainWindow
import json


class Controller:
    def __init__(self, main_window: QMainWindow, pyqt_slots: dict, pyqt_signals: dict):
        self.main_window = main_window
        # self.application = application
        self.control_thread = threading.Thread(target=self.run)
        self.params = None
        self.sources = []
        self.credentials = dict()
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.source_last_processed_frame_id = dict()
        self.detectors = []
        self.trackers = []
        self.obj_handler = None
        self.visualizer = None
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self.fps = 5

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

        self.captured_frames: list[CaptureImage] = []
        self.detection_results: list[DetectionResultList] = []
        self.tracking_results: list[TrackingResultList] = []
        self.run_flag = False

        self.gui_enabled = True
        self.autoclose = False

        self.current_main_widget_size = [1920, 1080]

    def is_running(self):
        return self.run_flag

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Get new frames from all sources
            self.captured_frames = []
            all_sources_finished = True
            debug_info = dict()

            for source in self.sources:
                frames = source.get_frames()

                if len(frames) == 0:
                    if not source.is_finished():
                        all_sources_finished = False
                else:
                    all_sources_finished = False
                    self.captured_frames.extend(frames)

            if self.autoclose and all_sources_finished:
                self.run_flag = False
                #break

            if self.run_flag:
                for source in self.sources:
                    if not source.is_running():
                        source.start()

            complete_capture_it = timer()

            # Process detectors
            processing_frames = []
            self.detection_results = []
            debug_info["detectors"] = dict()
            for detector in self.detectors:
                det_debug_info = debug_info["detectors"][detector.get_id()] = dict()
                detector.get_debug_info(det_debug_info)
                source_ids = detector.get_source_ids()
                for capture_frame in self.captured_frames:
                    if capture_frame.source_id in source_ids:
                        if detector.put(capture_frame):
                            processing_frames.append(capture_frame)
                detection_result = detector.get()
                if detection_result:
                    self.detection_results.append(detection_result)

            complete_detection_it = timer()

            # Process trackers
            self.tracking_results = []
            for tracker in self.trackers:
                source_ids = tracker.get_source_ids()
                for det_result, image in self.detection_results:
                    if det_result.source_id in source_ids:
                        tracker.put((det_result, image))
                track_info = tracker.get()
                if track_info:
                    tracking_result, image = track_info
                    self.tracking_results = tracking_result
                    self.obj_handler.put((tracking_result, image))
                    self.source_last_processed_frame_id[image.source_id] = image.frame_id
            complete_tracking_it = timer()

            events = dict()
            events = self.events_detectors_controller.get()
            # print(events)
            if events:
                self.events_processor.put(events)
            complete_processing_it = timer()

            if self.gui_enabled:
                objects = []
                for i in range(len(self.visualizer.source_ids)):
                    objects.append(self.obj_handler.get('active', self.visualizer.source_ids[i]))
                complete_read_objects_it = timer()
                self.visualizer.update(processing_frames, self.source_last_processed_frame_id, objects, debug_info)
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
            # print(f"Time: cap[{complete_capture_it-begin_it}], det[{complete_detection_it-complete_capture_it}], track[{complete_tracking_it-complete_detection_it}], read=[{complete_read_objects_it-complete_tracking_it}], vis[{end_it-complete_read_objects_it}] = {end_it-begin_it} secs, sleep {sleep_seconds} secs")
            time.sleep(sleep_seconds)

    def start(self):
        for source in self.sources:
            source.start()
        for detector in self.detectors:
            detector.start()
        for tracker in self.trackers:
            tracker.start()
        self.obj_handler.start()
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
        self.db_adapter_cam_events.stop()
        self.db_adapter_fov_events.stop()
        self.db_adapter_zone_events.stop()
        self.db_adapter_obj.stop()
        self.db_controller.disconnect()
        self.visualizer.stop()
        self.obj_handler.stop()
        for tracker in self.trackers:
            tracker.stop()
        for detector in self.detectors:
            detector.stop()
        for source in self.sources:
            source.stop()
        print('Everything in controller stopped')

    def init(self, params):
        self.params = params

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
        except FileNotFoundError as ex:
            pass

        self._init_captures(self.params['sources'])
        self._init_detectors(self.params['detectors'])
        self._init_trackers(self.params['trackers'])
        self._init_visualizer(self.params['visualizer'])
        self._init_db_controller(self.params['database'], system_params=self.params)
        self._init_db_adapters(self.params['database_adapters'])
        self.__init_object_handler(self.db_controller, params['objects_handler'])
        self._init_events_detectors(self.params['events_detectors'])
        self._init_events_detectors_controller(self.params['events_detectors'])
        self._init_events_processor(self.params['events_processor'])

        self.autoclose = self.params['controller'].get("autoclose", False)
        self.fps = self.params['controller'].get("fps", 5)
        self.class_names = self.params['controller'].get("class_names", list())

    def release(self):
        self.stop()

        for tracker in self.trackers:
            tracker.release()
        for detector in self.detectors:
            detector.release()
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
            camera_creds = self.credentials.get(src_params["camera"], None)
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
            tracker = object_tracking_botsort.ObjectTrackingBotsort()
            tracker.set_params(**tracker_params)
            tracker.init()
            self.trackers.append(tracker)

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

    # def _save_video_duration(self):
    #     self.db_controller.update_video_dur(self.source_video_duration)
