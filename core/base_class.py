from abc import ABC, abstractmethod


class EvilEyeBase(ABC):
    def __init__(self):
        self.is_inited = False
        self.params = {}

    def set_params(self, **params):
        self.params = params
        self.set_params_impl()

    def get_init_flag(self):
        return self.is_inited

    def reset(self):
        if self.get_init_flag():
            self.reset_impl()

    def init(self):
        if not self.get_init_flag():
            self.is_inited = self.init_impl()

    def release(self):
        self.release_impl()
        self.is_inited = False

    def get_params(self):
        return self.params

    @abstractmethod
    def default(self):
        pass

    @abstractmethod
    def init_impl(self):
        pass

    @abstractmethod
    def release_impl(self):
        pass

    @abstractmethod
    def reset_impl(self):
        pass

    @abstractmethod
    def set_params_impl(self):
        pass
