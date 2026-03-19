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

        def _normalize_result_meta(result):
            """
            Ensure result metadata matches the paired frame.
            Contract for downstream (ObjectsHandler/Visualizer): if result is (data, Frame),
            then data.source_id/frame_id/time_stamp must equal Frame.source_id/frame_id/time_stamp when those attrs exist.
            """
            try:
                if not (isinstance(result, (list, tuple)) and len(result) >= 2):
                    return result
                data = result[0]
                frame = result[1]
                if data is None or frame is None:
                    return result
                if hasattr(data, "source_id") and hasattr(frame, "source_id"):
                    data.source_id = frame.source_id
                if hasattr(data, "frame_id") and hasattr(frame, "frame_id"):
                    data.frame_id = frame.frame_id
                if hasattr(data, "time_stamp") and hasattr(frame, "time_stamp"):
                    data.time_stamp = frame.time_stamp
            except Exception:
                pass
            return result

        # Drain outputs from all processors.
        # Previously output queues were effectively unbounded so slow draining didn't surface as "queue full"
        # (but could accumulate memory). Now that outputs are bounded, we must drain more than 1 item per tick.
        max_items_per_processor = 64
        for processor in self.processors:
            drained = 0
            while drained < max_items_per_processor:
                result = processor.get()
                if not result:
                    break
                processing_results.append(_normalize_result_meta(result))
                drained += 1

        return processing_results