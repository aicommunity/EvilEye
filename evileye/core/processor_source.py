from .base_class import EvilEyeBase
from .processor_base import ProcessorBase


class ProcessorSource(ProcessorBase):
    def __init__(
        self,
        processor_name,
        class_name,
        num_processors: int,
        order: int,
        class_names: list[str] | None = None,
    ):
        super().__init__(
            processor_name, class_name, num_processors, order, class_names=class_names
        )

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
            # Finished streams should not be respawned on every pipeline tick.
            # A failed/uninitialized source remains retryable until it reports
            # completion through is_finished().
            if not processor.is_running() and not processor.is_finished():
                processor.start()
