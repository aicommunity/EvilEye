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

        for processor in self.processors:
            result = processor.get()
            if result:
                processing_results.append(result)

        # Always return original data if no results from processors
        if not processing_results and frames_list is not None:
            processing_results = frames_list

        return processing_results