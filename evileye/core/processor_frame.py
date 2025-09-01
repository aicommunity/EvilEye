from .processor_base import ProcessorBase


class ProcessorFrame(ProcessorBase):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        super().__init__(processor_name, class_name, num_processors, order)

    def process(self, frames_list=None):
        processing_results = []
        if frames_list is not None:
            for frame in frames_list:
                is_processor_found = False
                for processor in self.processors:
                    source_ids = processor.get_source_ids()
                    if frame.source_id in source_ids:
                        processor.put(frame)
                        is_processor_found = True

                    if is_processor_found:
                        break

                if not is_processor_found:
                    processing_results.append(frame)

        for processor in self.processors:
            result = processor.get()
            if result:
                processing_results.append(result)

        return processing_results