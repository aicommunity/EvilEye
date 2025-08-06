from core import EvilEyeBase, ProcessorBase


class ProcessorSource(ProcessorBase):
    def __init__(self, class_name, num_processors: int, order: int):
        super().__init__(class_name, num_processors, order)

    def process(self, frames_list=None):
        processing_results = []
        all_sources_finished = True
        for processor in self.processors:
            result = processor.get()
            if len(result) == 0:
                if not processor.is_finished():
                    all_sources_finished = False
            else:
                all_sources_finished = False
                processing_results.extend(result)
        return processing_results, all_sources_finished

    def run_sources(self):
        for processor in self.processors:
            if not processor.is_running():
                processor.start()