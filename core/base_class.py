from abc import ABC, abstractmethod
from pympler import asizeof
import datetime


class EvilEyeBase(ABC):
    id_counter = 0
    def __init__(self):
        self.is_inited = False
        self.id: int = EvilEyeBase.id_counter
        EvilEyeBase.id_counter += 1
        self.params = {}
        self.memory_measure_results = None
        self.memory_measure_time = None

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

    def get_debug_info(self, debug_info: dict | None):
        if debug_info is None:
            debug_info = dict()
        debug_info['id'] = self.id
        debug_info['is_inited'] = self.is_inited
        debug_info['memory_measure_results'] = self.memory_measure_results
        debug_info['memory_measure_time'] = self.memory_measure_time

    def insert_debug_info_by_id(self, debug_info: dict | None):
        if debug_info is None:
            debug_info = dict()
        comp_debug_info = debug_info[self.id] = dict()
        self.get_debug_info(comp_debug_info)
        return debug_info[self.id]

    def calc_memory_consumption(self):
        self.memory_measure_results = asizeof.asizeof(self)
        self.memory_measure_time = datetime.datetime.now()


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
