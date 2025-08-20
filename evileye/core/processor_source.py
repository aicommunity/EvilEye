from .base_class import EvilEyeBase
from .processor_base import ProcessorBase


class ProcessorSource(ProcessorBase):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        super().__init__(processor_name, class_name, num_processors, order)

    def process(self, frames_list=None):
        processing_results = []
        all_sources_finished = True
        for i, processor in enumerate(self.processors):
            result = processor.get()
            if len(result) == 0:
                if not processor.is_finished():
                    all_sources_finished = False
            else:
                all_sources_finished = False
                processing_results.extend(result)
        return processing_results

    def check_all_sources_finished(self):
        all_sources_finished = True
        for processor in self.processors:
            if not processor.is_finished():
                all_sources_finished = False
        return all_sources_finished

    def run_sources(self):
        for processor in self.processors:
            if not processor.is_running():
                processor.start()