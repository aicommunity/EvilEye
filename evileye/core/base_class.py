from abc import ABC, abstractmethod
from pympler import asizeof
import datetime
import logging


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
        # Runtime capabilities for pipeline compatibility checks.
        self.accepts_frame_handle = False
        self.emits_dto_type = None
        self.requires_materialized_frame = True
        self.logger_name = None
        self.memory_measure_results = None
        self.memory_measure_time = None
        # Автоматическая инициализация логгера для всех наследников
        # Имя логгера: evileye.{classlower}[{id}] или evileye.{classlower}[{id}].{logger_name}
        # Используется для компонентов с lifecycle (наследники EvilEyeBase)
        self._init_logger()

    def _init_logger(self):
        """
        Инициализировать логгер для компонента с lifecycle.
        
        Этот метод используется компонентами, наследующимися от EvilEyeBase,
        и создает логгер с уникальным идентификатором экземпляра в имени.
        Формат: evileye.{classname}[{id}] или evileye.{classname}[{id}].{logger_name}
        
        Для модулей без lifecycle используйте get_module_logger() из logger.py
        """
        try:
            base_name = f"evileye.{self.__class__.__name__.lower()}[{self.id}]"
            full_name = f"{base_name}.{self.logger_name}" if self.logger_name else base_name
            self.logger = logging.getLogger(full_name)
        except Exception:
            self.logger = logging.getLogger("evileye")

    def set_params(self, **params):
        self.params = params
        # Опционально переименовать логгер, если задано имя
        if 'logger_name' in params and params['logger_name']:
            self.logger_name = params['logger_name']
            self._init_logger()
        self.set_params_impl()

    def get_params(self):
        self.params = self.get_params_impl()
        return self.params

    def get_capability_metadata(self) -> dict:
        """Return runtime capability metadata used by pipeline validation."""
        return {
            "accepts_frame_handle": bool(getattr(self, "accepts_frame_handle", False)),
            "emits_dto_type": getattr(self, "emits_dto_type", None),
            "requires_materialized_frame": bool(
                getattr(self, "requires_materialized_frame", True)
            ),
        }

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

    def _check_interface_compliance(self, protocol_class) -> bool:
        """
        Проверить соответствие экземпляра Protocol интерфейсу (для отладки).
        
        Этот метод использует runtime проверку Protocol через isinstance().
        Используется только для отладки и валидации соответствия интерфейсам.
        
        Args:
            protocol_class: Класс Protocol (например, IPipeline, IObjectHandler)
            
        Returns:
            True если экземпляр соответствует Protocol, False иначе
            
        Note:
            Protocols в Python используют структурную типизацию, поэтому
            isinstance() проверяет наличие методов, а не наследование.
            Для production кода используйте type hints вместо runtime проверок.
            
        Example:
            pipeline = PipelineSurveillance()
            if pipeline._check_interface_compliance(IPipeline):
                print("Pipeline соответствует IPipeline")
        """
        try:
            from typing import Protocol
            if isinstance(protocol_class, type) and issubclass(protocol_class, Protocol):
                return isinstance(self, protocol_class)
        except Exception:
            pass
        return False
