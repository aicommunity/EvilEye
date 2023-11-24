import base_class as core
from abc import ABC, abstractmethod


class ObjectDetector(core.BaseClass):
    def process(self, image, all_roi=None):
        if self.get_init_flag():
            return self.process_impl(image, all_roi)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, image, roi):
        pass
