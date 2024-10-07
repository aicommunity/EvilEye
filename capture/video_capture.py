import cv2
import capture
from capture import VideoCaptureBase as Base
from threading import Lock
import time
from timeit import default_timer as timer
from capture.video_capture_base import CaptureImage
from enum import IntEnum


class VideoCapture(capture.VideoCaptureBase):
    class VideoCaptureAPIs(IntEnum):
        CAP_ANY = 0
        CAP_GSTREAMER = 1800
        CAP_FFMPEG = 1900
        CAP_IMAGES = 2000

    def __init__(self):
        super().__init__()
        self.capture = cv2.VideoCapture()
        self.mutex = Lock()

    def is_opened(self):
        return self.capture.isOpened()

    def release(self):
        self.capture.release()

    def set_params_impl(self):
        self.release()
        self.split_stream = self.params.get('split', False)
        self.num_split = self.params.get('num_split', None)
        self.src_coords = self.params.get('src_coords', None)

    def init_impl(self):
        if self.params['source'] == 'IPcam' and self.params['apiPreference'] == "CAP_GSTREAMER":  # Приведение rtsp ссылки к формату gstreamer
            if '!' not in self.params['camera']:
                str_h265 = (' ! rtph265depay ! h265parse ! avdec_h265 ! decodebin ! videoconvert ! '  # Указание кодеков и форматов
                            'video/x-raw, format=(string)BGR ! appsink')
                str_h264 = (' ! rtph264depay ! h264parse ! avdec_h264 ! decodebin ! videoconvert ! '
                            'video/x-raw, format=(string)BGR ! appsink')

                if self.params['camera'].find('tcp') == 0:  # Задание протокола
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='
                elif self.params['camera'].find('udp') == 0:
                    str1 = 'rtspsrc protocols=' + 'udp ' + 'location='
                else:
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='

                pos = self.params['camera'].find('rtsp')
                source = str1 + self.params['camera'][pos:] + str_h265
                self.capture.open(source, VideoCapture.VideoCaptureAPIs[self.params['apiPreference']])
                if not self.is_opened():  # Если h265 не подойдет, используем h264
                    source = str1 + self.params['camera'] + str_h264
                    self.capture.open(source, VideoCapture.VideoCaptureAPIs[self.params['apiPreference']])
            else:
                self.capture.open(self.params['camera'], VideoCapture.VideoCaptureAPIs[self.params['apiPreference']])
        else:
            self.capture.open(self.params['camera'], VideoCapture.VideoCaptureAPIs[self.params['apiPreference']])

        self.source_fps = None
        if self.capture.isOpened():
            try:
                self.source_fps = self.capture.get(cv2.CAP_PROP_FPS)
                if self.source_fps == 0.0:
                    self.source_fps = None
            except cv2.error as e:
                print(f"Failed to read source_fps: {e} for camera {self.params['camera']}")
        else:
            print(f"Could not connect to a camera: {self.params['camera']}")
            return False

        return True

    def release_impl(self):
        self.capture.release()

    def reset_impl(self):
        self.release()
        self.init()

    def _capture_frames(self):
        while self.run_flag:
            begin_it = timer()
            is_read, src_image = self.capture.read()
            if is_read:
                with self.mutex:
                    if self.frames_queue.full():
                        self.frames_queue.get()
                self.frames_queue.put([is_read, src_image, self.frame_id_counter])
                self.frame_id_counter += 1
            else:
                with self.mutex:
                    if self.frames_queue.full():
                        self.frames_queue.get()
                self.frames_queue.put([is_read, None, None])
            end_it = timer()
            elapsed_seconds = end_it - begin_it

            if self.source_fps:
                sleep_seconds = 1. / self.source_fps - elapsed_seconds
                if sleep_seconds <= 0.0:
                    sleep_seconds = 0.001
            else:
                sleep_seconds = 0.03
            time.sleep(sleep_seconds)

        if not self.run_flag:
            while not self.frames_queue.empty:
                self.frames_queue.get()

    def get_frames_impl(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        ret, src_image, frame_id = self.frames_queue.get()
        if ret:
            if self.split_stream:  # Если сплит, то возвращаем список с частями потока, иначе - исходное изображение
                for stream_cnt in range(self.num_split):
                    capture_image = CaptureImage()
                    capture_image.source_id = self.params["source_ids"][stream_cnt]
                    capture_image.time_stamp = time.time()
                    capture_image.frame_id = frame_id
                    capture_image.image = src_image[self.src_coords[stream_cnt][1]:self.src_coords[stream_cnt][1] + int(self.src_coords[stream_cnt][3]),
                                   self.src_coords[stream_cnt][0]:self.src_coords[stream_cnt][0] + int(self.src_coords[stream_cnt][2])].copy()
                    captured_images.append(capture_image)
            else:
                capture_image = CaptureImage()
                capture_image.source_id = self.params["source_ids"][0]
                capture_image.time_stamp = time.time()
                capture_image.frame_id = frame_id
                capture_image.image = src_image
                captured_images.append(capture_image)
        return captured_images


    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()
