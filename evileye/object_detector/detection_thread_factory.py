"""
Factory for creating detection threads.
"""

from typing import Type, Optional
from queue import Queue
import logging

from .detection_thread_base import DetectionThreadBase
from .detection_thread_yolo import DetectionThreadYolo
from .detection_thread_rtdetr import DetectionThreadRtdetr
from .detection_thread_rfdetr import DetectionThreadRfdetr
from .detection_thread_yolo_mp import DetectionThreadYoloMp


class DetectionThreadFactory:
    """Factory for creating detection thread instances."""

    _thread_classes = {
        "yolo": DetectionThreadYolo,
        "rtdetr": DetectionThreadRtdetr,
        "rfdetr": DetectionThreadRfdetr,
        "yolo_mp": DetectionThreadYoloMp,
    }

    @classmethod
    def create_thread(
        cls,
        thread_type: str,
        model_name: str,
        stride: int,
        classes: list,
        source_ids: list,
        roi: list,
        inf_params: dict,
        queue_out: Queue,
        logger_name: Optional[str] = None,
        parent_logger: Optional[logging.Logger] = None,
    ) -> DetectionThreadBase:
        """
        Create a detection thread instance.
        """
        thread_class = cls._thread_classes.get(thread_type.lower())
        if thread_class is None:
            raise ValueError(
                f"Unsupported thread type: {thread_type}. Supported types: {list(cls._thread_classes.keys())}"
            )

        # YoloMp doesn't support logger_name and parent_logger
        if thread_type.lower() == "yolo_mp":
            return thread_class(model_name, stride, classes, source_ids, roi, inf_params, queue_out)

        return thread_class(
            model_name,
            stride,
            classes,
            source_ids,
            roi,
            inf_params,
            queue_out,
            logger_name=logger_name,
            parent_logger=parent_logger,
        )

    @classmethod
    def register_thread_class(cls, thread_type: str, thread_class: Type[DetectionThreadBase]) -> None:
        """Register a new thread class type."""
        if not issubclass(thread_class, DetectionThreadBase):
            raise TypeError("thread_class must be a subclass of DetectionThreadBase")
        cls._thread_classes[thread_type.lower()] = thread_class

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported thread types."""
        return list(cls._thread_classes.keys())

"""
Factory for creating detection threads.
"""

from typing import Type, Optional
from queue import Queue
import logging
from .detection_thread_base import DetectionThreadBase
from .detection_thread_yolo import DetectionThreadYolo
from .detection_thread_rtdetr import DetectionThreadRtdetr
from .detection_thread_rfdetr import DetectionThreadRfdetr
from .detection_thread_yolo_mp import DetectionThreadYoloMp


class DetectionThreadFactory:
    """Factory for creating detection thread instances."""
    
    _thread_classes = {
        'yolo': DetectionThreadYolo,
        'rtdetr': DetectionThreadRtdetr,
        'rfdetr': DetectionThreadRfdetr,
        'yolo_mp': DetectionThreadYoloMp,
    }
    
    @classmethod
    def create_thread(
        cls,
        thread_type: str,
        model_name: str,
        stride: int,
        classes: list,
        source_ids: list,
        roi: list,
        inf_params: dict,
        queue_out: Queue,
        logger_name: Optional[str] = None,
        parent_logger: Optional[logging.Logger] = None,
    ) -> DetectionThreadBase:
        """
        Create a detection thread instance.
        
        Args:
            thread_type: Type of thread ('yolo', 'rtdetr', 'rfdetr', 'yolo_mp')
            model_name: Path to model file
            stride: Frame stride parameter
            classes: List of class IDs or names to detect
            source_ids: List of source IDs
            roi: ROI coordinates
            inf_params: Inference parameters dictionary
            queue_out: Output queue for results
            logger_name: Optional logger name
            parent_logger: Optional parent logger instance
            
        Returns:
            DetectionThreadBase instance
            
        Raises:
            ValueError: If thread_type is not supported
        """
        thread_class = cls._thread_classes.get(thread_type.lower())
        if thread_class is None:
            raise ValueError(f"Unsupported thread type: {thread_type}. "
                           f"Supported types: {list(cls._thread_classes.keys())}")
        
        # YoloMp doesn't support logger_name and parent_logger
        if thread_type.lower() == 'yolo_mp':
            return thread_class(
                model_name, stride, classes, source_ids, roi, inf_params, queue_out
            )
        else:
            return thread_class(
                model_name, stride, classes, source_ids, roi, inf_params, queue_out,
                logger_name=logger_name, parent_logger=parent_logger
            )
    
    @classmethod
    def register_thread_class(cls, thread_type: str, thread_class: Type[DetectionThreadBase]):
        """
        Register a new thread class type.
        
        Args:
            thread_type: Type identifier (e.g., 'custom')
            thread_class: DetectionThreadBase subclass
        """
        if not issubclass(thread_class, DetectionThreadBase):
            raise TypeError(f"thread_class must be a subclass of DetectionThreadBase")
        cls._thread_classes[thread_type.lower()] = thread_class
    
    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported thread types."""
        return list(cls._thread_classes.keys())
