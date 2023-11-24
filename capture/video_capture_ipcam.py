import cv2
import video_capture_base as base


class VideoCaptureIpCam(base.VideoCapture):
    def set_params_impl(self):
        self.capture.open(**self.params)

    def reset_impl(self):
        pass

    def process_impl(self):
        is_read, image = self.capture.read()
        return is_read, image

    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()

    def init_impl(self):
        return True
