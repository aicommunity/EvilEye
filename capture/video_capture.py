import cv2
import capture
from capture import VideoCaptureBase as Base
from threading import Thread
from queue import Queue
from threading import Lock


class VideoCapture(capture.VideoCaptureBase):
    def __init__(self):
        super().__init__()
        self.mutex = Lock()
        self.frames_queue = Queue(maxsize=2)
        self.writer = Thread(target=self._capture_frames, daemon=True)

    def set_params_impl(self):
        source = None
        if self.params['source'] == 'IPcam' and self.params['apiPreference'] == "CAP_GSTREAMER":  # Приведение rtsp ссылки к формату gstreamer
            if '!' not in self.params['filename']:
                str_h265 = (' ! rtph265depay ! h265parse ! avdec_h265 ! decodebin ! videoconvert ! '  # Указание кодеков и форматов
                            'video/x-raw, format=(string)BGR ! appsink')
                str_h264 = (' ! rtph264depay ! h264parse ! avdec_h264 ! decodebin ! videoconvert ! '
                            'video/x-raw, format=(string)BGR ! appsink')

                if self.params['filename'].find('tcp') == 0:  # Задание протокола
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='
                elif self.params['filename'].find('udp') == 0:
                    str1 = 'rtspsrc protocols=' + 'udp ' + 'location='
                else:
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='

                pos = self.params['filename'].find('rtsp')
                source = str1 + self.params['filename'][pos:] + str_h265
                self.capture.open(source, Base.VideoCaptureAPIs[self.params['apiPreference']])
                if not self.is_opened():  # Если h265 не подойдет, используем h264
                    source = str1 + self.params['filename'] + str_h264
                    self.capture.open(source, Base.VideoCaptureAPIs[self.params['apiPreference']])
            else:
                self.capture.open(self.params['filename'], Base.VideoCaptureAPIs[self.params['apiPreference']])
        else:
            self.capture.open(self.params['filename'], Base.VideoCaptureAPIs[self.params['apiPreference']])

    def init_impl(self):
        self.writer.start()
        return True

    def reset_impl(self):
        if self.params['source'] in ['file', 'sequence']:
            self.capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)  # Запустить видео заново
        else:  # Перезапускаем в случае разрыва соединения
            self.capture = cv2.VideoCapture(self.params['filename'], Base.VideoCaptureAPIs[self.params['apiPreference']])
            if not self.is_opened():  # Если переподключиться не получилось, бросаем исключение
                raise Exception("Could not connect to a camera: {0}".format(self.params['filename']))
            print("Connected to a camera: {0}".format(self.params['filename']))

    def _capture_frames(self):
        while True:
            # print('CAPTURING')
            is_read, src_image = self.capture.read()
            # print(is_read)
            if is_read:
                with self.mutex:
                    if self.frames_queue.full():
                        self.frames_queue.get_nowait()
                self.frames_queue.put([is_read, src_image])
            else:
                with self.mutex:
                    if self.frames_queue.full():
                        self.frames_queue.get_nowait()
                self.frames_queue.put([is_read, src_image])

    def process_impl(self, split_stream=False, num_split=None, src_coords=None):
        ret, src_image = self.frames_queue.get()
        # print('GOT')
        if ret:
            streams = []
            if split_stream:  # Если сплит, то возвращаем список с частями потока, иначе - исходное изображение
                for stream_cnt in range(num_split):
                    streams.append(src_image[src_coords[stream_cnt][1]:src_coords[stream_cnt][1] + int(src_coords[stream_cnt][3]),
                                   src_coords[stream_cnt][0]:src_coords[stream_cnt][0] + int(src_coords[stream_cnt][2])].copy())
            else:
                streams = [src_image]
            return ret, streams
        else:
            return False, None

    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()
