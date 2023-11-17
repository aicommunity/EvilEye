from abc import ABC, abstractmethod


class BackgroundSubtractor(ABC):
    def __init__(self):
        self.is_inited = False

    def get_init_flag(self):
        return self.is_inited

    def reset(self):
        if self.get_init_flag():
            self.areset()
        else:
            return -1       # Возможно, здесь необходимо исключение?

    def apply(self, image):
        if self.get_init_flag():
            self.apply(image)
        else:
            return -1

    @abstractmethod
    def apply(self, image):
        pass

    @abstractmethod
    def init(self):
        pass

    @abstractmethod
    def areset(self):
        pass

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
