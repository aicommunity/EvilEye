import threading
import capture
from object_detector import object_detection_yolov8
from object_tracker import object_tracking_botsort
from video_thread import VideoThread
from objects_handler import objects_handler
from time import sleep


class Controller:

    def __init__(self, pyqt_slot):
        self.control_thread = threading.Thread(target=self.run, daemon=True)
        self.params = None
        self.sources = []
        self.detectors = []
        self.trackers = []
        self.obj_handler = None
        self.visual_threads = []
        self.qt_slot = pyqt_slot

        self.num_sources = 0
        self.num_dets = 0
        self.num_tracks = 0
        self.captures = None
        self.detections = None
        self.track_info = None

    def run(self):
        while True:
            for i in range(self.num_sources):
                source = self.sources[i]
                # if source:
                self.captures[i] = source.process(split_stream=source.params['split'],
                                                  num_split=source.params['num_split'],
                                                  src_coords=source.params['src_coords'])
                # else:
                #     raise Exception('Source has not been set in the configuration file')

            for i in range(self.num_sources):
                is_read, frames = self.captures[i]
                if is_read:
                    # if not detectors:
                    #     raise Exception('Detector has not been set in the configuration file')

                    for count, frame in enumerate(frames):
                        detector = self.detectors[i + count]
                        detector.put((frame, count))
                        # frame_objects = detectors[count].process(frame, all_roi=detectors[count].params['roi'][count])
                        self.detections[i + count] = detector.get()
                        # print(self.detections[i + count])
                        # self.visual_threads[i + count].append_data((frame, self.detections[i + count]))
                else:
                    self.sources[i].reset()

            for i in range(self.num_sources):
                is_read, frames = self.captures[i]
                if is_read:
                    # if not detectors:
                    #     raise Exception('Detector has not been set in the configuration file
                    for count, frame in enumerate(frames):
                        # for j in range(self.num_tracks):
                        #     detection = self.detections[j]
                        #     print(detection)
                        # if not trackers:
                        #     raise Exception('Tracker has not been set in the configuration file')
                        tracker = self.trackers[i + count]
                        tracker.put(self.detections[i + count])
                        self.track_info[i + count] = tracker.get()
                        self.obj_handler.append(self.track_info[i + count])
                        # print(self.obj_handler.get('active', i + count))
                        self.visual_threads[i + count].append_data((frame, self.obj_handler.get('active', i + count)))
                else:
                    self.sources[i].reset()

            sleep(0.01)

    def init(self, params):
        self.params = params
        self.num_sources = len(self.params['sources'])
        self.num_dets = len(self.params['detectors'])
        self.num_tracks = len(self.params['trackers'])
        self.captures = [None] * self.num_sources
        self.detections = [None] * self.num_dets
        self.track_info = [None] * self.num_tracks

        self._init_captures(self.params['sources'])
        self._init_detectors(self.params['detectors'])
        self._init_trackers(self.params['trackers'])
        self._init_visualizer()
        self.obj_handler = objects_handler.ObjectsHandler(self.num_tracks, history_len=30)
        self.control_thread.start()

    def _init_captures(self, params):
        num_sources = len(params)
        for i in range(num_sources):
            src_params = params[i]
            # print(src_params)
            camera = capture.VideoCapture()
            camera.set_params(**src_params)
            camera.init()
            self.sources.append(camera)

    def _init_detectors(self, params):
        num_det = len(params)
        for i in range(num_det):
            det_params = params[i]
            # print(det_params)
            self.detectors.append(object_detection_yolov8.ObjectDetectorYoloV8())
            self.detectors[i].set_params(**det_params)
            self.detectors[i].init()

    def _init_trackers(self, params):
        num_trackers = len(params)
        for i in range(num_trackers):
            self.trackers.append(object_tracking_botsort.ObjectTrackingBotsort())
            self.trackers[i].init()

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
                    self.visual_threads[-1].start()
            else:
                self.visual_threads.append(VideoThread(self.params['sources'][i], self.params['num_height'],
                                                       self.params['num_width']))
                self.visual_threads[-1].update_image_signal.connect(
                    self.qt_slot)  # Сигнал из потока для обновления label на новое изображение
                self.visual_threads[-1].start()
