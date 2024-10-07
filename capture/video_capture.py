import cv2
import capture
from capture import VideoCaptureBase as Base
from threading import Lock
import time
from time import sleep
from capture.video_capture_base import CaptureImage


class VideoCapture(capture.VideoCaptureBase):
    def __init__(self):
        super().__init__()
        self.mutex = Lock()

    def set_params_impl(self):
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
                self.capture.open(source, Base.VideoCaptureAPIs[self.params['apiPreference']])
                if not self.is_opened():  # Если h265 не подойдет, используем h264
                    source = str1 + self.params['camera'] + str_h264
                    self.capture.open(source, Base.VideoCaptureAPIs[self.params['apiPreference']])
            else:
                self.capture.open(self.params['camera'], Base.VideoCaptureAPIs[self.params['apiPreference']])
        else:
            self.capture.open(self.params['camera'], Base.VideoCaptureAPIs[self.params['apiPreference']])

    def init_impl(self):
        return True

    def reset_impl(self):
        if self.params['source'] in ['file', 'sequence']:
            self.capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)  # Запустить видео заново
        else:  # Перезапускаем в случае разрыва соединения
            self.capture = cv2.VideoCapture(self.params['camera'], Base.VideoCaptureAPIs[self.params['apiPreference']])
            if not self.is_opened():  # Если переподключиться не получилось, бросаем исключение
                raise Exception("Could not connect to a camera: {0}".format(self.params['camera']))
            print("Connected to a camera: {0}".format(self.params['camera']))

    def _capture_frames(self):
        while self.run_flag:
            sleep(0.01)
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
        if not self.run_flag:
            while not self.frames_queue.empty:
                self.frames_queue.get()

    def process_impl(self, split_stream=False, num_split=None, src_coords=None):
        captured_images: list[CaptureImage] = []
        ret, src_image, frame_id = self.frames_queue.get()
        # print('GOT')
        if ret:
            if split_stream:  # Если сплит, то возвращаем список с частями потока, иначе - исходное изображение
                for stream_cnt in range(num_split):
                    capture_image = CaptureImage()
                    capture_image.source_id = self.params["source_ids"][stream_cnt]
                    capture_image.time_stamp = time.time()
                    capture_image.frame_id = frame_id
                    capture_image.image = src_image[src_coords[stream_cnt][1]:src_coords[stream_cnt][1] + int(src_coords[stream_cnt][3]),
                                   src_coords[stream_cnt][0]:src_coords[stream_cnt][0] + int(src_coords[stream_cnt][2])].copy()
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
