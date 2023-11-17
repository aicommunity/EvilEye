from abc import ABC, abstractmethod


class ObjectDetector(ABC):

    def __init__(self):
        self.is_inited = False
        self.params = {}

    def get_init_flag(self):
        return self.is_inited

    def get_params(self):
        return self.params

    def reset(self):
        if self.get_init_flag():
            self.areset()
        else:
            return -1

    def detect(self, image, all_roi):
        if self.get_init_flag():
            self.adetect(image, all_roi)
        else:
            return -1

    @abstractmethod
    def init(self):
        pass
    @abstractmethod
    def areset(self):
        pass

    @abstractmethod
    def adetect(self, image, roi):
        pass

    @abstractmethod
    def set_params(self, **params):
        pass

    @abstractmethod
    def default(self):
        pass
