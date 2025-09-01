import datetime

import cv2
from threading import Lock
import time
from timeit import default_timer as timer
from .video_capture_base import VideoCaptureBase, CaptureImage, CaptureDeviceType
from enum import IntEnum

from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("VideoCapture")
class VideoCapture(VideoCaptureBase):
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

    def set_params_impl(self):
        super().set_params_impl()

    def init_impl(self):
        api_pref = self.params.get('apiPreference','CAP_FFMPEG')
        if self.source_type == CaptureDeviceType.IpCamera and api_pref == "CAP_GSTREAMER":  # Приведение rtsp ссылки к формату gstreamer
            if '!' not in self.source_address:
                str_h265 = (' ! rtph265depay ! h265parse ! avdec_h265 ! decodebin ! videoconvert ! '  # Указание кодеков и форматов
                            'video/x-raw, format=(string)BGR ! appsink')
                str_h264 = (' ! rtph264depay ! h264parse ! avdec_h264 ! decodebin ! videoconvert ! '
                            'video/x-raw, format=(string)BGR ! appsink')

                if self.source_address.find('tcp') == 0:  # Задание протокола
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='
                elif self.source_address.find('udp') == 0:
                    str1 = 'rtspsrc protocols=' + 'udp ' + 'location='
                else:
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='

                pos = self.source_address.find('rtsp')
                source = str1 + self.source_address[pos:] + str_h265
                self.capture.open(source, VideoCapture.VideoCaptureAPIs[api_pref])
                if not self.is_opened():  # Если h265 не подойдет, используем h264
                    source = str1 + self.source_address + str_h264
                    self.capture.open(source, VideoCapture.VideoCaptureAPIs[api_pref])
            else:
                self.capture.open(self.source_address, VideoCapture.VideoCaptureAPIs[api_pref])
        else:
            self.capture.open(self.source_address, VideoCapture.VideoCaptureAPIs[api_pref])

        self.source_fps = None
        if self.capture.isOpened():
            self.is_working = True
            if self.source_type == CaptureDeviceType.VideoFile:
                self.video_length = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
                self.video_current_frame = 0
                self.video_current_position = 0.0
            self.finished = False
            try:
                self.source_fps = self.capture.get(cv2.CAP_PROP_FPS)
                if self.source_fps == 0.0:
                    self.source_fps = None
                    self.video_duration = None
                print(f'FPS: {self.source_fps}')

                if self.source_fps is not None and self.source_type == CaptureDeviceType.VideoFile:
                    self.video_duration = self.video_length * 1000.0 / self.source_fps
            except cv2.error as e:
                print(f"Failed to read source_fps: {e} for sources {self.source_names}")
        else:
            print(f"Could not connect to a sources: {self.source_names}")
            self.video_duration = None
            self.video_length = None
            self.video_current_frame = None
            self.video_current_position = None
            return False

        return True

    def release_impl(self):
        self.capture.release()

    def reset_impl(self):
        self.release()
        self.init()
        timestamp = datetime.datetime.now()
        if self.get_init_flag() and self.is_opened():
            print(f"Reconnected to a sources: {self.source_names}")
            self.is_working = True
            self.reconnects.append((self.params['camera'], timestamp, self.is_working))
        else:
            print(f"Could not connect to sources: {self.source_names}")
        for sub in self.subscribers:
            sub.update()

    def _grab_frames(self):
        while self.run_flag:
            begin_it = timer()
            if not self.is_inited or self.capture is None:
                time.sleep(0.1)
                if self.init():
                    timestamp = datetime.datetime.now()
                    print(f"Reconnected to a sources: {self.source_names}")
                    self.reconnects.append((self.params['camera'], timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                else:
                    continue

            if not self.is_opened():
                time.sleep(0.1)
                self.reset()

            is_grabbed = False
            with self.mutex:
                is_grabbed = self.capture.grab()
            if not is_grabbed:
                if self.source_type != CaptureDeviceType.VideoFile or self.loop_play:
                    self.is_working = False
                    timestamp = datetime.datetime.now()
                    self.disconnects.append((self.params['camera'], timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                    self.reset()
                else:
                    self.finished = True

            end_it = timer()
            elapsed_seconds = end_it - begin_it
            if self.source_fps:
                fps_multiplier = 1.5 if self.source_type == CaptureDeviceType.IpCamera else 1.0
                sleep_seconds = 1. / (fps_multiplier * self.source_fps) - elapsed_seconds
                if sleep_seconds <= 0.0:
                    sleep_seconds = 0.001
            else:
                sleep_seconds = 0.03
            time.sleep(sleep_seconds)

    def _retrieve_frames(self):
        while self.run_flag:
            begin_it = timer()
            is_read, src_image = None, None
            with self.mutex:
                is_read, src_image = self.capture.retrieve()
            if is_read:
                if self.frames_queue.full():
                    self.frames_queue.get()
                if self.source_type == CaptureDeviceType.VideoFile:
                    self.video_current_frame += 1
                    if self.source_fps and self.source_fps > 0.0:
                        self.video_current_position = (self.video_current_frame * 1000.0) / self.source_fps
                if self.source_type == CaptureDeviceType.IpCamera:
                    self.last_frame_time = datetime.datetime.now()
                self.frames_queue.put([is_read, src_image, self.frame_id_counter, self.video_current_frame, self.video_current_position])
                self.frame_id_counter += 1

            end_it = timer()
            elapsed_seconds = end_it - begin_it

            retrieve_fps = self.desired_fps if self.desired_fps else self.source_fps if self.source_fps else 15
            sleep_seconds = 1. / retrieve_fps - elapsed_seconds
            if sleep_seconds <= 0.0:
                sleep_seconds = 0.001

            time.sleep(sleep_seconds)

        if not self.run_flag:
            print('Not run flag')
            while not self.frames_queue.empty:
                self.frames_queue.get()

        if not self.run_flag:
            print('Not run flag')
            while not self.frames_queue.empty:
                self.frames_queue.get()

    def get_frames_impl(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.frames_queue.empty():
            return captured_images
        ret, src_image, frame_id, current_video_frame, current_video_position = self.frames_queue.get()
        if ret:
            if self.split_stream:  # Если сплит, то возвращаем список с частями потока, иначе - исходное изображение
                for stream_cnt in range(self.num_split):
                    capture_image = CaptureImage()
                    capture_image.source_id = self.source_ids[stream_cnt]
                    capture_image.time_stamp = time.time()
                    capture_image.frame_id = frame_id
                    capture_image.current_video_frame = current_video_frame
                    capture_image.current_video_position = current_video_position
                    capture_image.image = src_image[self.src_coords[stream_cnt][1]:self.src_coords[stream_cnt][1] + int(self.src_coords[stream_cnt][3]),
                                          self.src_coords[stream_cnt][0]:self.src_coords[stream_cnt][0] + int(self.src_coords[stream_cnt][2])].copy()
                    captured_images.append(capture_image)
            else:
                capture_image = CaptureImage()
                capture_image.source_id = self.source_ids[0]
                capture_image.time_stamp = time.time()
                capture_image.frame_id = frame_id
                capture_image.current_video_frame = current_video_frame
                capture_image.current_video_position = current_video_position
                capture_image.image = src_image
                captured_images.append(capture_image)
        return captured_images

    def default(self):
        pass

    def test_disconnect(self):
        with self.conn_mutex:
            timestamp = datetime.datetime.now()
            print(f'Disconnect: {timestamp}')
            is_working = False
            self.disconnects.append((self.source_address, timestamp, is_working))

    def test_reconnect(self):
        with self.conn_mutex:
            timestamp = datetime.datetime.now()
            print(f'Reconnect: {timestamp}')
            is_working = True
            self.reconnects.append((self.source_address, timestamp, is_working))
