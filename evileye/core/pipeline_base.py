from .base_class import EvilEyeBase
from abc import abstractmethod
from typing import List, Dict, Any, Optional
from queue import Queue


class PipelineBase(EvilEyeBase):
    """
    Base class for all pipeline implementations.
    Contains common functionality not related to processors.
    """
    
    def __init__(self):
        super().__init__()
        self._credentials = None
        
        # Results storage for external access
        self._results_queue: Queue = Queue(maxsize=2)
        self._current_results: Dict[str, Any] = {}
        self._final_results_name: str|None = None

    def default(self):
        """Reset pipeline to default state"""
        self._credentials = {}
        # Clear the queue
        while not self._results_queue.empty():
            try:
                self._results_queue.get_nowait()
            except:
                pass
        self._current_results = {}

    def set_credentials(self, credentials):
        """Set credentials for pipeline components"""
        self._credentials = credentials

    def get_credentials(self):
        """Get current credentials"""
        return self._credentials

    def init_impl(self, **kwargs):
        """Initialize pipeline implementation - override in subclasses"""
        return True

    def release_impl(self):
        """Release pipeline resources - override in subclasses"""
        pass

    def reset_impl(self):
        """Reset pipeline state - override in subclasses"""
        # Clear the queue
        while not self._results_queue.empty():
            try:
                self._results_queue.get_nowait()
            except:
                pass
        self._current_results = {}

    def set_params_impl(self):
        """Set pipeline parameters from self.params - override in subclasses"""
        pass

    def get_params_impl(self):
        """Get pipeline parameters - override in subclasses"""
        params = {}
        params["pipeline_class"] = self.__class__.__name__
        return params

    def start(self):
        """Start pipeline - override in subclasses"""
        pass

    def stop(self):
        """Stop pipeline - override in subclasses"""
        pass

    def process(self) -> Dict[str, Any]:
        """
        Process pipeline and return results.
        This is the main method that should be implemented by derived classes.
        
        Returns:
            Dictionary with processing results
        """
        raise NotImplementedError("Subclasses must implement process()")

    def get_results_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all results from pipeline processing.
        This method is used by the controller to access results.
        
        Returns:
            List of result dictionaries
        """
        # Return empty list if queue is empty
        if self._results_queue.empty():
            return []
        
        # Convert queue to list efficiently
        results = []
        temp_queue = Queue()
        
        # Copy all items from the original queue
        while not self._results_queue.empty():
            try:
                item = self._results_queue.get_nowait()
                results.append(item)
                temp_queue.put(item)
            except:
                break
        
        # Restore the original queue
        while not temp_queue.empty():
            try:
                self._results_queue.put(temp_queue.get_nowait())
            except:
                break
        
        return results

    def get_current_results(self) -> Dict[str, Any]:
        """
        Get current processing results.
        
        Returns:
            Dictionary with current results
        """
        return self._current_results

    def add_result(self, result: Dict[str, Any]):
        """
        Add result to the results queue.
        If queue is full, automatically remove oldest result.
        
        Args:
            result: Result dictionary to add
        """
        # If queue is full, remove oldest result automatically
        if self._results_queue.full():
            try:
                self._results_queue.get_nowait()  # Remove oldest result
            except:
                pass
        
        # Add new result
        self._results_queue.put(result)
        self._current_results = result

    def clear_results(self):
        """Clear all stored results"""
        # Clear the queue
        while not self._results_queue.empty():
            try:
                self._results_queue.get_nowait()
            except:
                pass
        self._current_results = {}

    def get_result_count(self) -> int:
        """
        Get number of stored results.
        
        Returns:
            Number of results
        """
        return self._results_queue.qsize()

    def get_latest_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent result.
        
        Returns:
            Latest result dictionary or None if no results
        """
        if self._results_queue.empty():
            return None
        
        # Get the latest result without removing it from queue
        latest_result = None
        temp_queue = Queue()
        
        # Copy all items to find the latest
        while not self._results_queue.empty():
            try:
                item = self._results_queue.get_nowait()
                latest_result = item
                temp_queue.put(item)
            except:
                break
        
        # Restore the original queue
        while not temp_queue.empty():
            try:
                self._results_queue.put(temp_queue.get_nowait())
            except:
                break
        
        return latest_result
    
    def get_results_queue(self) -> Queue:
        """
        Get the results queue directly.
        
        Returns:
            Queue containing results
        """
        return self._results_queue
    
    def is_results_queue_full(self) -> bool:
        """
        Check if results queue is full.
        
        Returns:
            True if queue is full, False otherwise
        """
        return self._results_queue.full()
    
    def get_results_queue_size(self) -> int:
        """
        Get the current size of the results queue.
        
        Returns:
            Current number of items in the queue
        """
        return self._results_queue.qsize()
    
    def peek_latest_result(self) -> Optional[Dict[str, Any]]:
        """
        Peek at the latest result without removing it from queue.
        More efficient than get_latest_result() for frequent access.
        
        Returns:
            Latest result dictionary or None if no results
        """
        if self._results_queue.empty():
            return None
        
        # Use a more efficient approach for single item access
        try:
            # Get all items temporarily
            items = []
            while not self._results_queue.empty():
                items.append(self._results_queue.get_nowait())
            
            # Restore all items
            for item in items:
                self._results_queue.put(item)
            
            # Return the last item if any
            return items[-1] if items else None
        except:
            return None
    
    def get_results_iterator(self):
        """
        Get an iterator over all results in the queue.
        This is more memory efficient than get_results_list() for large queues.
        
        Returns:
            Iterator over results
        """
        if self._results_queue.empty():
            return iter([])
        
        # Create a temporary queue to preserve original
        temp_queue = Queue()
        results = []
        
        # Copy all items
        while not self._results_queue.empty():
            try:
                item = self._results_queue.get_nowait()
                results.append(item)
                temp_queue.put(item)
            except:
                break
        
        # Restore the original queue
        while not temp_queue.empty():
            try:
                self._results_queue.put(temp_queue.get_nowait())
            except:
                break
        
        return iter(results)

    def get_final_results_name(self):
        return self._final_results_name

    def check_all_sources_finished(self) -> bool:
        """
        Check if all sources have finished processing.
        Override in subclasses that have sources.
        
        Returns:
            True if all sources finished, False otherwise
        """
        return True

    def calc_memory_consumption(self):
        """
        Calculate memory consumption.
        Override in subclasses that need memory tracking.
        """
        self.memory_measure_results = 0

    def get_dropped_ids(self) -> List[int]:
        """
        Get dropped frame IDs.
        Override in subclasses that track dropped frames.
        
        Returns:
            List of dropped frame IDs
        """
        return []

    def insert_debug_info_by_id(self, debug_info: Dict[str, Any]):
        """
        Insert debug information into debug_info dict.
        Override in subclasses that provide debug information.
        
        Args:
            debug_info: Dictionary to store debug information
        """
        pass

    @abstractmethod
    def get_sources(self) -> List:
        """
        Get video sources for external subscriptions (events, etc.).
        This method is used by the controller to access video sources.
        
        Returns:
            List of video sources (CaptureImage objects or similar)
        """
        pass

    @abstractmethod
    def generate_default_structure(self, num_sources: int):
        """
        Generate default structure for pipeline.
        This method should be implemented by derived classes.
        
        Args:
            num_sources: Number of sources to configure
        """
        pass
