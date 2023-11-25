import cv2
import capture


class VideoCaptureSeq(capture.VideoCaptureBase):
    def set_params_impl(self):
        self.capture.open(**self.params)

    def reset_impl(self):
        self.capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)  # Отображать последовательность с начала

    def process_impl(self):
        is_read, image = self.capture.read()
        return is_read, image

    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()

    def init_impl(self):
        return True
