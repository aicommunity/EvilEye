from abc import ABC, abstractmethod
import base_class as core


class BackgroundSubtractor(core.BaseClass):
    def process(self, image):
        if self.get_init_flag():
            return self.process_impl(image)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, image):
        pass
