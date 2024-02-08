from abc import ABC, abstractmethod
import core


class ObjectTrackingBase(core.EvilEyeBase):
    def process(self, image, bboxes):
        if self.get_init_flag():
            return self.process_impl(image, bboxes)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, image, bboxes):
        pass
