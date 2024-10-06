import threading
import capture
from object_detector import object_detection_yolov8
from object_detector.object_detection_base import DetectionResultList
from object_tracker import object_tracking_botsort
from video_thread import VideoThread
from objects_handler import objects_handler
from time import sleep
from capture.video_capture_base import CaptureImage


class Controller:

    def __init__(self, pyqt_slot):
        self.control_thread = threading.Thread(target=self.run)
        self.params = None
        self.sources = []
        self.detectors = []
        self.trackers = []
        self.obj_handler = None
        self.visual_threads = []
        self.qt_slot = pyqt_slot

        self.num_videos = 0
        self.num_sources = 0
        self.num_dets = 0
        self.num_tracks = 0
        self.captured_frames: list[CaptureImage] = []
        self.detection_results: list[DetectionResultList] = []
        self.track_info = None
        self.run_flag = False

    def run(self):
        while self.run_flag:
            self.captured_frames = []
            for i in range(self.num_sources):
                source = self.sources[i]
                frames = source.process(split_stream=source.params['split'],
                                                 num_split=source.params['num_split'],
                                                 src_coords=source.params['src_coords'])
                self.captured_frames.extend(frames)

#                if not is_read:
#                    source.reset()

            det_params = self.params['detectors']
            for i in range(self.num_dets):
                detector = self.detectors[i]
                source_ids = det_params[i]['source_ids']
                for capture_frame in self.captured_frames:
                    if capture_frame.source_id in source_ids:
                        detector.put(capture_frame)

            self.detection_results = []
            for i in range(self.num_dets):
                detection_result = self.detectors[i].get()
                if detection_result:
                    self.detection_results.append(detection_result)

            tr_params = self.params['trackers']
            for i in range(self.num_tracks):
                tracker = self.trackers[i]
                source_ids = tr_params[i]['source_ids']
                for det_result in self.detection_results:
                    if det_result.source_id in source_ids:
                        tracker.put(det_result)

            self.track_info = []
            for i in range(self.num_tracks):
                track_info = self.trackers[i].get()
                if track_info:
                    self.track_info = track_info
                    self.obj_handler.append(track_info)

            for i in range(self.num_videos):
                self.visual_threads[i].append_data((self.captured_frames[i], self.obj_handler.get('active', i)))
            sleep(0.01)

    def start(self):
        for source in self.sources:
            source.start()
        for detector in self.detectors:
            detector.start()
        for tracker in self.trackers:
            tracker.start()
        self.obj_handler.start()
        for thread in self.visual_threads:
            thread.start_thread()
        self.run_flag = True
        self.control_thread.start()

    def stop(self):
        self.run_flag = False
        self.control_thread.join()
        for thread in self.visual_threads:
            thread.stop()
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
        self.num_sources = len(self.params['sources'])
        self.num_dets = len(self.params['detectors'])
        self.num_tracks = len(self.params['trackers'])

        self._init_captures(self.params['sources'])
        self._init_detectors(self.params['detectors'])
        self._init_trackers(self.params['trackers'])
        self._init_visualizer()
        self.obj_handler = objects_handler.ObjectsHandler(self.num_videos, history_len=30)

    def _init_captures(self, params):
        num_sources = len(params)
        num_videos = 0
        for i in range(num_sources):
            src_params = params[i]
            if src_params['split']:
                num_videos += src_params['num_split']
            else:
                num_videos += 1

            camera = capture.VideoCapture()
            camera.set_params(**src_params)
            camera.init()
            self.sources.append(camera)
        self.captured_frames = [None] * num_videos
        self.num_videos = num_videos

    def _init_detectors(self, params):
        num_det = len(params)
        for i in range(num_det):
            det_params = params[i]

            detector = object_detection_yolov8.ObjectDetectorYoloV8()
            self.detectors.append(detector)
            detector.set_params(**det_params)
            detector.init()
        self.detection_results = [None] * self.num_videos

    def _init_trackers(self, params):
        num_trackers = len(params)
        for i in range(num_trackers):
            tracker = object_tracking_botsort.ObjectTrackingBotsort()
            self.trackers.append(tracker)
            tracker.init()
        self.track_info = [None] * self.num_videos

    def _init_visualizer(self):
        num_videos = len(self.params['sources'])
        src_params = []

        for i in range(num_videos):
            source = self.params['sources'][i]
            if source['split']:
                for j in range(source['num_split']):
                    self.visual_threads.append(VideoThread(self.params['sources'][i], self.params['num_height'],
                                                           self.params['num_width']))
                    self.visual_threads[-1].update_image_signal.connect(
                        self.qt_slot)  # Сигнал из потока для обновления label на новое изображение
            else:
                self.visual_threads.append(VideoThread(self.params['sources'][i], self.params['num_height'],
                                                       self.params['num_width']))
                self.visual_threads[-1].update_image_signal.connect(
                    self.qt_slot)  # Сигнал из потока для обновления label на новое изображение
