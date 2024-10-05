import threading
import capture
from object_detector import object_detection_yolov8
from object_tracker import object_tracking_botsort
from video_thread import VideoThread
from objects_handler import objects_handler
from time import sleep


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
        self.captured_frames = None
        self.detections = None
        self.track_info = None
        self.run_flag = False

    def run(self):
        while self.run_flag:
            for i in range(self.num_sources):
                source = self.sources[i]
                is_read, frames = source.process(split_stream=source.params['split'],
                                                 num_split=source.params['num_split'],
                                                 src_coords=source.params['src_coords'])
                if frames is not None:
                    for frame_count, frame in enumerate(frames):
                        self.captured_frames[i + frame_count] = frame
                    # print(frame)

                if not is_read:
                    source.reset()

            det_params = self.params['detectors']
            for i in range(self.num_dets):
                detector = self.detectors[i]
                cameras = det_params[i]['cameras']
                batch = []
                for cam_num in cameras:
                    if self.captured_frames[cam_num] is not None:
                        if len(cameras) > 1:
                            batch.append((self.captured_frames[cam_num], cam_num))
                        else:
                            detector.put((self.captured_frames[cam_num], cam_num))
                if batch:
                    detector.put(batch)

            for i in range(self.num_dets):
                detection = self.detectors[i].get()
                cam_num = detection['cam_id']
                self.detections[cam_num] = detection

            for i in range(self.num_tracks):
                tracker = self.trackers[i]
                cameras = det_params[i]['cameras']
                batch = []
                for cam_num in cameras:
                    if len(cameras) > 1:
                        batch.append((self.detections[cam_num], cam_num))
                    else:
                        tracker.put(self.detections[cam_num])
                if batch:
                    tracker.put(batch)

            for i in range(self.num_tracks):
                track_info = self.trackers[i].get()
                cam_num = track_info['cam_id']
                self.track_info[cam_num] = track_info

            for tracks in self.track_info:
                self.obj_handler.append(tracks)

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
        self.detections = [None] * self.num_videos

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
