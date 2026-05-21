from .base_class import EvilEyeBase
from abc import ABC, abstractmethod
from .logger import get_module_logger
import threading
import os

EXEC_MODE_THREAD = "thread"
EXEC_MODE_PROCESS = "process"


class ProcessorBase(ABC):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        # Используем get_module_logger(), т.к. ProcessorBase не наследуется от EvilEyeBase
        # и не имеет lifecycle (init/release). Это контейнер для процессоров, а не компонент с lifecycle.
        self.logger = get_module_logger("processor_base")
        self.processor_name = processor_name
        self.class_name = class_name
        self.params = None
        self.num_processors = num_processors
        self.order = order
        # Создание процессоров вынесено в отдельный метод для снижения связности
        self.dummy_processor = self._create_processor_instance(class_name)
        self.execution_mode = EXEC_MODE_THREAD
        self.ipc_mode = "standard"
        self.dummy_processor = self._create_processor_instance(class_name)
        self.processors = []
        for i in range(0, num_processors):
            processor = self._create_processor_instance(class_name)
            processor.set_id(i)
            self.processors.append(processor)

    def _create_processor_instance(self, class_name: str) -> EvilEyeBase:
        """
        Создать экземпляр процессора через plugin-регистр.
        
        Этот метод изолирует создание процессоров от прямого вызова
        EvilEyeBase.create_instance(), что позволяет в будущем заменить
        механизм создания (например, для тестирования с моками).
        
        Args:
            class_name: Имя класса процессора, зарегистрированного через @EvilEyeBase.register
            
        Returns:
            Экземпляр процессора (наследник EvilEyeBase)
            
        Raises:
            ValueError: Если класс не найден в plugin-регистре
            
        Note:
            Зависит от EvilEyeBase._registry и декоратора @EvilEyeBase.register.
            Для тестирования можно переопределить этот метод в подклассах.
        """
        return EvilEyeBase.create_instance(class_name)

    def get_processors(self):
        return self.processors

    def get_name(self):
        return self.processor_name

    def set_params(self, params):
        self.params = params
        if len(params) != self.num_processors or type(params) != list:
            self.logger.error(
                f"Failed to initialize processors {self.class_name}[{self.num_processors}]. Wrong params list.")

        # Detect execution_mode from the first param block (shared across all)
        if params and isinstance(params, list) and len(params) > 0:
            self.execution_mode = params[0].get('execution_mode', EXEC_MODE_THREAD)
            self.ipc_mode = params[0].get("ipc_mode", "standard")

        for i in range(0, self.num_processors):
            self.processors[i].set_params(**params[i])
            self._validate_processor_capabilities(self.processors[i], i)

    def _validate_processor_capabilities(self, processor: EvilEyeBase, idx: int) -> None:
        """Warn about incompatible stage capabilities for selected transport mode."""
        try:
            if self.ipc_mode != "descriptor":
                return
            accepts_frame_handle = bool(
                getattr(processor, "accepts_frame_handle", False)
            )
            if not accepts_frame_handle:
                self.logger.warning(
                    "Processor %s[%d] (%s) does not declare descriptor transport "
                    "support; running in standard payload mode for this stage",
                    self.processor_name,
                    idx,
                    processor.__class__.__name__,
                )
        except Exception:
            pass

    def get_params(self):
        processors_params = list()
        for processor in self.processors:
            processors_params.append(processor.get_params())

        return processors_params

    def init(self, **kwargs):
        init_success = True
        for i, processor in enumerate(self.processors):
            try:
                result = processor.init(**kwargs)
                if not result:
                    init_success = False
                    self.logger.warning(f"Processor {i} ({self.class_name}) init failed; reconnect logic will retry")
            except Exception as e:
                init_success = False
                self.logger.warning(
                    f"Processor {i} ({self.class_name}) init raised exception: {e}; reconnect logic will retry")
        return init_success

    def release(self):
        for processor in self.processors:
            processor.release()

    def start(self):
        for processor in self.processors:
            processor.start()

    def stop(self):
        stop_timeout_sec = float(os.getenv("EVILEYE_PROCESSOR_STOP_TIMEOUT_SEC", "8.0") or "8.0")
        for processor in self.processors:
            stop_done = threading.Event()
            stop_error: list[Exception] = []

            def _stop_processor():
                try:
                    processor.stop()
                except Exception as exc:
                    stop_error.append(exc)
                finally:
                    stop_done.set()

            threading.Thread(target=_stop_processor, daemon=True).start()
            if not stop_done.wait(stop_timeout_sec):
                try:
                    self.logger.warning(
                        "Inner processor stop timeout after %.1fs: container=%s class=%s processor=%s",
                        stop_timeout_sec,
                        self.processor_name,
                        self.class_name,
                        processor.__class__.__name__,
                    )
                except Exception:
                    pass
                try:
                    force_stop = getattr(processor, "force_stop", None)
                    if callable(force_stop):
                        force_stop()
                except Exception:
                    pass
                continue
            if stop_error:
                raise stop_error[0]

    def insert_debug_info_by_id(self, section_name: str, debug_info: dict):
        for processor in self.processors:
            processor.insert_debug_info_by_id(debug_info.setdefault(section_name, {}))

    def calc_memory_consumption(self):
        for processor in self.processors:
            processor.calc_memory_consumption()

    def get_memory_usage(self):
        total_memory_usage = 0
        debug_info = dict()
        debug_info["processors"] = dict()
        for processor in self.processors:
            comp_debug_info = processor.insert_debug_info_by_id(debug_info.setdefault("processors", {}))
            total_memory_usage += comp_debug_info["memory_measure_results"]
        return total_memory_usage

    def get_dropped_ids(self):
        dropped_ids = []
        for processor in self.processors:
            if not hasattr(processor, 'get_dropped_ids'):
                continue
            dropped_id = processor.get_dropped_ids()
            if len(dropped_id) > 0:
                dropped_ids.extend(dropped_id)
        return dropped_ids

    @abstractmethod
    def process(self, frames_list=None):
        pass
