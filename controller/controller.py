import threading
import capture
from object_detector import object_detection_yolov8
from object_detector.object_detection_base import DetectionResultList
from object_tracker import object_tracking_botsort
from object_tracker.object_tracking_base import TrackingResultList
from video_thread import VideoThread
from objects_handler import objects_handler
from time import sleep
from capture.video_capture_base import CaptureImage
import copy
import time
from timeit import default_timer as timer


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
        self.fps = 5

        self.captured_frames: list[CaptureImage] = []
        self.processed_frames: list[CaptureImage] = []
        self.detection_results: list[DetectionResultList] = []
        self.tracking_results: list[TrackingResultList] = []
        self.run_flag = False

    def run(self):
        while self.run_flag:
            begin_it = timer()
            # Get new frames from all sources
            self.captured_frames = []
            for source in self.sources:
                frames = source.get_frames()

                if len(frames) == 0:
                    pass
#                    source.reset()
                else:
                    self.captured_frames.extend(frames)

            complete_capture_it = timer()

            # Process detectors
            self.detection_results = []
            for detector in self.detectors:
                source_ids = detector.get_source_ids()
                for capture_frame in self.captured_frames:
                    if capture_frame.source_id in source_ids:
                        if detector.put(capture_frame):
                            self.processed_frames.append(capture_frame)
                detection_result = detector.get()
                if detection_result:
                    self.detection_results.append(detection_result)



            complete_detection_it = timer()

            # Process trackers
            self.tracking_results = []
            for tracker in self.trackers:
                source_ids = tracker.get_source_ids()
                for det_result in self.detection_results:
                    if det_result.source_id in source_ids:
                        tracker.put(det_result)
                track_info = tracker.get()
                if track_info:
                    self.tracking_results = track_info
                    self.obj_handler.append(track_info)

            complete_tracking_it = timer()

            # Process visualization
            remove_processed_idx = []
            for i in range(len(self.visual_threads)):
                objects = copy.deepcopy(self.obj_handler.get('active', i))
                last_frame_id = None
                if objects:
                    last_frame_id = objects.find_last_frame_id()

                if last_frame_id:
                    for j in range(len(self.processed_frames)):
                        if self.processed_frames[j].source_id == i:
                            if self.processed_frames[j].frame_id < last_frame_id:
                                remove_processed_idx.append(j)
                            if self.processed_frames[j].frame_id == last_frame_id:
                                self.visual_threads[i].append_data((copy.deepcopy(self.processed_frames[j]), objects))
                                break
                else:
                    for j in reversed(range(len(self.processed_frames))):
                        if self.processed_frames[j].source_id == i:
                            self.visual_threads[i].append_data((copy.deepcopy(self.processed_frames[j]), objects))
                            break

            remove_processed_idx.sort(reverse=True)
            for index in remove_processed_idx:
                del self.processed_frames[index]

            if len(self.processed_frames) > 30:
                del self.processed_frames[(len(self.processed_frames)-30):]

#            for j in range(len(self.processed_frames)):
#                visual_index = self.processed_frames[j].source_id
#                self.visual_threads[visual_index].append_data((copy.deepcopy(self.processed_frames[j]), copy.deepcopy(self.obj_handler.get('active', visual_index))))
#            self.processed_frames = []

            end_it = timer()
            elapsed_seconds = end_it - begin_it

            print(f"Time: cap[{complete_capture_it-begin_it}], det[{complete_detection_it-complete_capture_it}], track[{complete_tracking_it-complete_detection_it}], vis[{end_it-complete_tracking_it}] = {end_it-begin_it} secs")

            if self.fps:
                sleep_seconds = 1. / self.fps - elapsed_seconds
                if sleep_seconds <= 0.0:
                    sleep_seconds = 0.001
            else:
                sleep_seconds = 0.03
            time.sleep(sleep_seconds)

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

        self._init_captures(self.params['sources'])
        self._init_detectors(self.params['detectors'])
        self._init_trackers(self.params['trackers'])
        self._init_visualizer()
        self.obj_handler = objects_handler.ObjectsHandler(history_len=30)

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
