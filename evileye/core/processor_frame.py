from .processor_base import ProcessorBase


class ProcessorFrame(ProcessorBase):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        super().__init__(processor_name, class_name, num_processors, order)

    def process(self, frames_list=None):
        processing_results = []
        if frames_list is not None:
            # Handle both single Frame and list of frames
            if not isinstance(frames_list, (list, tuple)):
                # Single Frame object
                frames_list = [frames_list]

            for item in frames_list:
                # Handle both Frame objects and tuples [data, frame]
                if isinstance(item, tuple) and len(item) == 2:
                    data, frame = item
                    # For attributes processors, we only need the frame
                    frame_to_process = frame
                else:
                    # Assume it's a Frame object
                    frame_to_process = item

                is_processor_found = False
                for processor in self.processors:
                    source_ids = processor.get_source_ids()
                    if hasattr(frame_to_process, 'source_id') and frame_to_process.source_id in source_ids:
                        processor.put(frame_to_process)
                        is_processor_found = True

                    if is_processor_found:
                        break

                if not is_processor_found:
                    processing_results.append(item)

        def _normalize_result_meta(result):
            """
            Ensure result metadata matches the paired frame when processor returns (data, Frame).
            This keeps downstream frame/object matching deterministic without any fallbacks.
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
        # With bounded queues downstream must consume faster than 1 item/tick.
        max_items_per_processor = 64
        for processor in self.processors:
            drained = 0
            while drained < max_items_per_processor:
                result = processor.get()
                if not result:
                    break
                processing_results.append(_normalize_result_meta(result))
                drained += 1

        # Always return original data if no results from processors
        if not processing_results and frames_list is not None:
            processing_results = frames_list

        return processing_results
