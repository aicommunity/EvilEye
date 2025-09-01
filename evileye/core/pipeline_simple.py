from .pipeline_base import PipelineBase
from abc import abstractmethod
from typing import Dict, Any


class PipelineSimple(PipelineBase):
    """
    Simple pipeline implementation with abstract logic method.
    Suitable for pipelines that don't need complex processor management.
    """
    
    def __init__(self):
        super().__init__()
        self._is_running = False

    def start(self):
        """Start the simple pipeline"""
        self._is_running = True
        self.start_impl()

    def stop(self):
        """Stop the simple pipeline"""
        self._is_running = False
        self.stop_impl()

    def process(self) -> Dict[str, Any]:
        """
        Process pipeline and return results.
        Calls the abstract process_logic method and stores results.
        
        Returns:
            Dictionary with processing results
        """
        if not self._is_running:
            return {}
        
        # Call abstract method for actual processing logic
        result = self.process_logic()
        
        # Store result for external access
        if result:
            self.add_result(result)

        return result

    def is_running(self) -> bool:
        """
        Check if pipeline is running.
        
        Returns:
            True if pipeline is running, False otherwise
        """
        return self._is_running

    def reset_impl(self):
        """Reset pipeline state"""
        super().reset_impl()

    @abstractmethod
    def process_logic(self) -> Dict[str, Any]:
        """
        Abstract method for pipeline logic implementation.
        This method should be implemented by derived classes.
        
        Returns:
            Dictionary with processing results
        """
        pass

    def start_impl(self):
        """
        Implementation-specific start logic.
        Override in derived classes if needed.
        """
        pass

    def stop_impl(self):
        """
        Implementation-specific stop logic.
        Override in derived classes if needed.
        """
        pass

    def get_sources(self):
        """
        Get video sources for external subscriptions.
        Simple pipelines typically don't have video sources.
        
        Returns:
            Empty list since simple pipelines don't have video sources
        """
        return []

    def generate_default_structure(self, num_sources: int):
        """
        Generate default structure for simple pipeline.
        Override in derived classes if needed.
        
        Args:
            num_sources: Number of sources to configure
        """
        # Simple pipelines typically don't need complex structure generation
        pass
