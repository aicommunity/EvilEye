from abc import ABC, abstractmethod


class EvilEyeBase(ABC):
    def __init__(self):
        self.is_inited = False
        self.id : int = 0
        self.params = {}

    def set_params(self, **params):
        self.params = params
        self.set_params_impl()

    def get_init_flag(self):
        return self.is_inited

    def get_id(self):
        return self.id

    def set_id(self, id_value: int):
        self.id = id_value

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

    def get_debug_info(self, debug_info: dict):
        debug_info['is_inited'] = self.is_inited

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
