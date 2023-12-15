import cv2
import capture


class VideoCapture(capture.VideoCaptureBase):
    def set_params_impl(self):
        if self.get_init_flag():
            self.capture.open(self.params['filename'], self.params['apiPreference'])
        else:
            raise Exception('init function has not been called')

    def reset_impl(self):
        if self.params['source'] in ['file', 'sequence']:
            self.capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)  # Запустить видео заново
        else:
            pass

    def process_impl(self, split_stream=False, num_split=None, roi=None):
        is_read, src_image = self.capture.read()
        if split_stream:
            streams = []
            streams.append(src_image[0:int(roi[0][1]), 0:int(roi[0][2])].copy())
            for stream_cnt in range(num_split - 1):
                streams.append(src_image[roi[stream_cnt][1]:roi[stream_cnt][1]+int(roi[stream_cnt][3]),
                                         roi[stream_cnt][0]:roi[stream_cnt][0]+int(roi[stream_cnt][2])].copy())
            return is_read, streams
        else:
            return is_read, src_image

    def default(self):
        self.params.clear()
        self.capture = cv2.VideoCapture()

    def init_impl(self):
        return True
