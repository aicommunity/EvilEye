from abc import ABC, abstractmethod
from pympler import asizeof
import datetime


class EvilEyeBase(ABC):
    _id_counter = 0
    _registry = dict()

    ResultType = None

    @classmethod
    def register(cls, class_name):
        def inner_wrapper(wrapped_class):
            cls._registry[class_name] = wrapped_class

            return wrapped_class
        return inner_wrapper

    @classmethod
    def create_instance(cls, class_name, *args, **kwargs):
        if class_name not in cls._registry:
            raise ValueError(f"Class not found: {class_name}")
        return cls._registry[class_name](*args, **kwargs)

    def __init__(self):
        self.is_inited = False
        self.id: int = EvilEyeBase._id_counter
        EvilEyeBase._id_counter += 1
        self.params = {}
        self.memory_measure_results = None
        self.memory_measure_time = None

    def set_params(self, **params):
        self.params = params
        self.set_params_impl()

    def get_params(self):
        self.params = self.get_params_impl()
        return self.params

    def get_init_flag(self):
        return self.is_inited

    def get_id(self):
        return self.id

    def set_id(self, id_value: int):
        self.id = id_value

    def reset(self):
        if self.get_init_flag():
            self.reset_impl()

    def init(self, **kwargs):
        if not self.get_init_flag():
            self.is_inited = self.init_impl(**kwargs)
        return self.is_inited

    def release(self):
        self.release_impl()
        self.is_inited = False

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
    def init_impl(self, **kwargs):
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

    @abstractmethod
    def get_params_impl(self):
        pass