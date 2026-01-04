from .pipeline_base import PipelineBase
from .processor_source import ProcessorSource
from .processor_frame import ProcessorFrame
from .processor_step import ProcessorStep
from .processor_base import ProcessorBase
from abc import abstractmethod
from typing import List, Dict, Any, Optional, Tuple


class PipelineProcessors(PipelineBase):
    """
    Processor-based pipeline implementation.
    Manages multiple processors in a processing chain.
    """
    
    def __init__(self):
        super().__init__()
        
        # List of processor components in execution order
        self.processors: List[ProcessorBase] = []
        
        # Unified processor parameters storage: {processor_name: params_list}
        self._processor_params: Dict[str, List[Dict]] = {}
        
        # Encoders for tracking (can be overridden by derived classes)
        self.encoders: Dict[str, Any] = {}

        self.sources_proc: ProcessorSource | None = None

        self._final_results_name = ""

    def default(self):
        """Reset pipeline to default state"""
        super().default()
        self._processor_params = {}
        self.encoders = {}
        self.processors = []

    def set_credentials(self, credentials):
        """Set credentials for pipeline components"""
        super().set_credentials(credentials)

    def init_impl(self, **kwargs):
        """Initialize pipeline implementation with processors - override in subclasses"""
        # Derived classes should implement their own initialization logic
        return True

    def release_impl(self):
        """Release all pipeline processors in reverse order"""
        for processor in reversed(self.processors):
            if processor is not None:
                processor.release()

    def reset_impl(self):
        """Reset pipeline state"""
        # Default implementation - override in subclasses if needed
        return None

    def set_params_impl(self):
        """Set pipeline parameters from self.params - override in subclasses"""
        for section_name in self.params:
            section_params = self.params.get(section_name, []) or []
            self._processor_params[section_name] = section_params

    def get_params_impl(self):
        """Get parameters from all processors"""
        params = super().get_params_impl()
        
        # Get parameters from each processor type
        for processor in self.processors:
            if processor is not None:
                section_name = processor.get_name()
                params[section_name] = processor.get_params()
        
        return params

    def start(self):
        """Start all processors in order, with sources starting last to prevent queue overflow"""
        import time
        from ..object_detector.object_detection_base import ObjectDetectorBase
        from .processor_frame import ProcessorFrame
        
        # First, start all processors except sources (detectors, trackers, etc.)
        # This ensures they are ready to receive data before sources begin capturing
        detectors = []
        for processor in self.processors:
            if processor is not None and not isinstance(processor, ProcessorSource):
                processor.start()
                # Collect detectors to wait for model loading
                if isinstance(processor, ProcessorFrame):
                    # Check if this processor contains detectors
                    if hasattr(processor, 'processors'):
                        for p in processor.processors:
                            if isinstance(p, ObjectDetectorBase):
                                detectors.append(p)
        
        # Wait for all detectors to load their models before starting sources
        # This prevents queue overflow when sources start sending frames
        if detectors:
            self.logger.info(f"Waiting for {len(detectors)} detector(s) to load models...")
            all_ready = True
            for detector in detectors:
                if hasattr(detector, 'is_ready'):
                    ready = detector.is_ready(timeout=30.0)
                    if not ready:
                        self.logger.warning(f"Detector {detector.__class__.__name__} did not become ready within timeout")
                        all_ready = False
                    else:
                        self.logger.debug(f"Detector {detector.__class__.__name__} is ready")
                else:
                    # Fallback: wait a bit for models to load
                    time.sleep(2.0)
            if all_ready:
                self.logger.info("All detectors are ready")
            else:
                self.logger.warning("Some detectors may not be fully ready, but starting sources anyway")
            # Add additional delay after models are loaded to ensure processing threads are fully initialized
            time.sleep(0.5)
        else:
            # No detectors found, use a small delay as fallback
            time.sleep(1.0)
        
        # Finally, start sources last so they don't send frames before processors are ready
        for processor in self.processors:
            if processor is not None and isinstance(processor, ProcessorSource):
                processor.start()

    def stop(self):
        """Stop all processors in reverse order"""
        for processor in reversed(self.processors):
            if processor is not None:
                processor.stop()

    def check_all_sources_finished(self):
        if self.sources_proc is None:
            return True
        return self.sources_proc.check_all_sources_finished()

    def process(self) -> dict[Any, Any]:
        pipeline_results = dict()
        step_result = None
        tracking_results = None  # Store tracking results for attributes processors

        for processor in self.processors:
            if processor is None:
                continue
                
            if isinstance(processor, ProcessorSource):
                self.run_sources()
            
            step_result = processor.process(step_result)
            
            pipeline_results[processor.get_name()] = step_result
            
            # Store tracking results for attributes processors
            # Always use mc_trackers results for attributes, regardless of mc_trackers status
            if processor.get_name() == 'mc_trackers' and step_result is not None:
                tracking_results = step_result

        # Store results for external access
        if pipeline_results:
            self.add_result(pipeline_results)

        return pipeline_results

    def calc_memory_consumption(self):
        """Calculate memory consumption for all processors"""
        total = 0
        for processor in self.processors:
            if processor is not None:
                processor.calc_memory_consumption()
                total += processor.get_memory_usage()
        self.memory_measure_results = total

    def get_dropped_ids(self):
        """Get dropped frame IDs from all processors"""
        dropped = []
        for processor in self.processors:
            if processor is not None:
                dropped.extend(processor.get_dropped_ids())
        return dropped

    def insert_debug_info_by_id(self, debug_info: dict):
        """
        Insert debug information from all pipeline processors into debug_info dict.
        
        Args:
            debug_info: Dictionary to store debug information
        """
        for processor in self.processors:
            if processor is not None:
                processor.insert_debug_info_by_id(processor.get_name(), debug_info)

    def get_sources(self):
        """Get video sources for external subscriptions (events, etc.)"""
        return self.sources_proc.get_processors() if self.sources_proc else []

    def run_sources(self):
        """Run source processors"""
        for processor in self.processors:
            if isinstance(processor, ProcessorSource):
                processor.run_sources()
                break

    def get_processor_params(self, processor_name: str) -> List[Dict]:
        """Get parameters for specific processor type"""
        return self._processor_params.get(processor_name, [])

    def set_processor_params(self, processor_name: str, params: List[Dict]):
        """Set parameters for specific processor type"""
        self._processor_params[processor_name] = params

    # Protected methods for processor management
    def _add_processor(self, processor: ProcessorBase):
        """Add processor to the pipeline"""
        self.processors.append(processor)

        if isinstance(processor, ProcessorSource):
            self.sources_proc = processor
        self._final_results_name = processor.get_name()

    def generate_default_structure(self, num_sources: int):
        """Generate default structure for pipeline"""
        # Default implementation for processor-based pipelines
        pass

