import cv2
import capture


class VideoCaptureFile(capture.VideoCaptureBase):
    def set_params_impl(self):
        if self.get_init_flag():
            self.capture.open(**self.params)
        else:
            raise Exception('init function has not been called')

    def reset_impl(self):
        self.capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)  # Запустить видео заново

    def process_impl(self):
        is_read, image = self.capture.read()
        return is_read, image

    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()

    def init_impl(self):
        return True
