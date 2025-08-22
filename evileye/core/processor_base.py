from .base_class import EvilEyeBase
from abc import ABC, abstractmethod

class ProcessorBase(ABC):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        self.processor_name = processor_name
        self.class_name = class_name
        self.params = None
        self.num_processors = num_processors
        self.order = order
        self.dummy_processor = EvilEyeBase.create_instance(class_name)
        self.processors = []
        for i in range(0, num_processors):
            processor = EvilEyeBase.create_instance(class_name)
            processor.set_id(i)
            self.processors.append(processor)

    def get_processors(self):
        return self.processors

    def get_name(self):
        return self.processor_name

    def set_params(self, params):
        self.params = params
        if len(params) != self.num_processors or type(params) != list:
            print(f"Failed to initialize processors {self.class_name}[{self.num_processors}]. Wrong params list.")
        for i in range(0, self.num_processors):
            self.processors[i].set_params(**params[i])

    def get_params(self):
        processors_params = list()
        for processor in self.processors:
            processors_params.append(processor.get_params())

        return processors_params

    def init(self, **kwargs):
        for i, processor in enumerate(self.processors):
            processor.init(**kwargs)
        return True

    def release(self):
        for processor in self.processors:
            processor.release()

    def start(self):
        for processor in self.processors:
            processor.start()

    def stop(self):
        for processor in self.processors:
            processor.stop()

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