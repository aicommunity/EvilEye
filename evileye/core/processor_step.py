from .processor_base import ProcessorBase
from .frame import Frame


class ProcessorStep(ProcessorBase):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        super().__init__(processor_name, class_name, num_processors, order)

    def process(self, input_list=None):
        processing_results = []
        if input_list is not None:
            for input in input_list:
                is_processor_found = False
                if (type(input) == list or type(input) == tuple) and len(input) >= 2:
                    data = input[0]
                    frame = input[1]
                elif type(input) == Frame:
                    frame = input
                    data = None
                else:
                    raise RuntimeError(f"Wrong type for input data in processor: {self.class_name}")

                for processor in self.processors:
                    source_ids = processor.get_source_ids()
                    if frame.source_id in source_ids:
                        processor.put(input)
                        is_processor_found = True

                    if is_processor_found:
                        break

                if not is_processor_found:
                    res = self.dummy_processor.ResultType()
                    if res is not None:
                        if hasattr(res, "source_id"):
                            setattr(res, "source_id", frame.source_id)
                        if hasattr(res, "frame_id"):
                            setattr(res, "frame_id", frame.frame_id)
                        if hasattr(res, "time_stamp"):
                            setattr(res, "time_stamp", frame.time_stamp)
                        if hasattr(res, "generate_from"):
                            res.generate_from(data)

                    processing_results.append([res, frame])

        for processor in self.processors:
            result = processor.get()
            if result:
                processing_results.append(result)

        return processing_results