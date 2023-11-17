from abc import ABC, abstractmethod


class BackgroundSubtractor(ABC):
   
    @abstractmethod
    def set_params(self, **params):
        pass

    @abstractmethod
    def get_params(self):
        pass

    @abstractmethod
    def default(self):
        pass

    @abstractmethod
    def get_roi(self, image, foreground_mask):
        pass
