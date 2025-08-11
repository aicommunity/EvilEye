from core import EvilEyeBase
from abc import abstractmethod


class Pipeline(EvilEyeBase):
    """
    Base class for pipeline implementations.
    Defines the interface for processing pipelines.
    """
    
    def __init__(self):
        super().__init__()

    def default(self):
        """Default implementation - override in subclasses"""
        pass

    def init_impl(self, **kwargs):
        """Initialize pipeline implementation - override in subclasses"""
        return True

    def release_impl(self):
        """Release pipeline resources - override in subclasses"""
        pass

    def reset_impl(self):
        """Reset pipeline state - override in subclasses"""
        pass

    def set_params_impl(self):
        """Set pipeline parameters - override in subclasses"""
        pass

    def get_params_impl(self):
        """Get pipeline parameters - override in subclasses"""
        return {}

    @abstractmethod
    def start(self):
        """Start pipeline processing - override in subclasses"""
        pass

    @abstractmethod
    def stop(self):
        """Stop pipeline processing - override in subclasses"""
        pass

    @abstractmethod
    def process(self):
        """Process pipeline - override in subclasses"""
        pass

    @abstractmethod
    def calc_memory_consumption(self):
        """Calculate memory consumption - override in subclasses"""
        pass

    @abstractmethod
    def get_dropped_ids(self):
        """Get dropped frame IDs - override in subclasses"""
        pass

    def insert_debug_info_by_id(self, debug_info: dict):
        """
        Insert debug information from pipeline components into debug_info dict.
        This method should be called after processing to collect debug data.
        
        Args:
            debug_info: Dictionary to store debug information
        """
        pass