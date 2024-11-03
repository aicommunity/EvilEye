import threading
import capture
from object_detector import object_detection_yolov8
from object_detector.object_detection_base import DetectionResultList
from object_tracker import object_tracking_botsort
from object_tracker.object_tracking_base import TrackingResultList
from visualizer.video_thread import VideoThread
from objects_handler import objects_handler
from capture.video_capture_base import CaptureImage
import copy
import time
from timeit import default_timer as timer
from visualizer.visualizer import Visualizer
from database_controller.database_controller_pg import DatabaseControllerPg


class Controller:

    def __init__(self, pyqt_slot):
        self.control_thread = threading.Thread(target=self.run)
        self.params = None
        self.sources = []
        self.detectors = []
        self.trackers = []
        self.obj_handler = None
        self.visualizer = None
        self.qt_slot = pyqt_slot
        self.fps = 5
        self.db_controller = None

        self.captured_frames: list[CaptureImage] = []
        self.detection_results: list[DetectionResultList] = []
        self.tracking_results: list[TrackingResultList] = []
        self.run_flag = False

        self.current_main_widget_size = [1920, 1080]

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Get new frames from all sources
            self.captured_frames = []
            for source in self.sources:
                frames = source.get_frames()

                if len(frames) == 0:
                    pass
                else:
                    self.captured_frames.extend(frames)

            complete_capture_it = timer()

            # Process detectors
            processing_frames = []
            self.detection_results = []
            for detector in self.detectors:
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

            complete_tracking_it = timer()

            objects = []
            for i in range(len(self.visualizer.source_ids)):
                objects.append(copy.deepcopy(self.obj_handler.get('active', self.visualizer.source_ids[i])))
            self.visualizer.update(processing_frames, objects)

            end_it = timer()
            elapsed_seconds = end_it - begin_it

            if self.fps:
                sleep_seconds = 1. / self.fps - elapsed_seconds
                if sleep_seconds <= 0.0:
                    sleep_seconds = 0.001
            else:
                sleep_seconds = 0.03
            # print(f"Time: cap[{complete_capture_it-begin_it}], det[{complete_detection_it-complete_capture_it}], track[{complete_tracking_it-complete_detection_it}], vis[{end_it-complete_tracking_it}] = {end_it-begin_it} secs, sleep {sleep_seconds} secs")
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
        self.run_flag = True
        self.control_thread.start()

    def stop(self):
        self.run_flag = False
        self.db_controller.disconnect()
        self.control_thread.join()
        self.visualizer.stop()
        self.obj_handler.stop()
        for tracker in self.trackers:
            tracker.stop()
        for detector in self.detectors:
            detector.stop()
        for source in self.sources:
            source.stop()
        print('Everything stopped')

    def init(self, params):
        self.params = params

        self._init_captures(self.params['sources'])
        self._init_detectors(self.params['detectors'])
        self._init_trackers(self.params['trackers'])
        self._init_visualizer(self.params['visualizer'])
        self._init_db_controller(self.params['database'])
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=self.db_controller, history_len=30)

    def set_current_main_widget_size(self, width, height):
        self.current_main_widget_size = [width, height]
        self.visualizer.set_current_main_widget_size(width, height)

    def _init_db_controller(self, params):
        self.db_controller = DatabaseControllerPg()
        self.db_controller.set_params(**params)
        self.db_controller.init()

    def _init_captures(self, params):
        num_sources = len(params)
        for i in range(num_sources):
            src_params = params[i]
            camera = capture.VideoCapture()
            camera.set_params(**src_params)
            camera.init()
            self.sources.append(camera)

    def _init_detectors(self, params):
        num_det = len(params)
        for i in range(num_det):
            det_params = params[i]

            detector = object_detection_yolov8.ObjectDetectorYoloV8()
            detector.set_params(**det_params)
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

    def _init_visualizer(self, params):
        self.visualizer = Visualizer(self.qt_slot)
        self.visualizer.set_params(**params)
        self.visualizer.init()
