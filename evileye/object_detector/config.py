"""
Configuration classes for object detectors.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import (
    DEFAULT_CONFIDENCE,
    DEFAULT_INFERENCE_SIZE,
    DEFAULT_NUM_DETECTION_THREADS,
    DEFAULT_STRIDE,
)


@dataclass
class InferenceParams:
    """Parameters for model inference."""

    show: bool = False
    conf: float = DEFAULT_CONFIDENCE
    save: bool = False
    imgsz: int = DEFAULT_INFERENCE_SIZE
    device: Optional[str] = None
    half: bool = True
    batch_size: Optional[int] = None  # Optional batch size for batching frames
    batch_timeout_ms: Optional[int] = None  # Optional timeout for forming a batch

    @classmethod
    def from_dict(cls, params: dict) -> "InferenceParams":
        """Create InferenceParams from dictionary."""
        return cls(
            show=params.get("show", False),
            conf=params.get("conf", DEFAULT_CONFIDENCE),
            save=params.get("save", False),
            imgsz=params.get("inference_size", params.get("imgsz", DEFAULT_INFERENCE_SIZE)),
            device=params.get("device", None),
            half=params.get("half", True),
            batch_size=params.get("batch_size", None),
            batch_timeout_ms=params.get("batch_timeout_ms", None),
        )

    def to_dict(self) -> dict:
        """Convert InferenceParams to dictionary."""
        return {
            "show": self.show,
            "conf": self.conf,
            "save": self.save,
            "imgsz": self.imgsz,
            "device": self.device,
            "half": self.half,
            "batch_size": self.batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
        }


@dataclass
class DetectorConfig:
    """Configuration for object detector."""

    stride: int = DEFAULT_STRIDE
    num_detection_threads: int = DEFAULT_NUM_DETECTION_THREADS
    inference_params: Optional[InferenceParams] = None

    @classmethod
    def from_dict(cls, params: dict) -> "DetectorConfig":
        """Create DetectorConfig from dictionary."""
        return cls(
            stride=params.get("vid_stride", DEFAULT_STRIDE),
            num_detection_threads=params.get("num_detection_threads", DEFAULT_NUM_DETECTION_THREADS),
            inference_params=InferenceParams.from_dict(params),
        )

"""
Configuration classes for object detectors.
"""

from dataclasses import dataclass
from typing import Optional
from .constants import (
    DEFAULT_CONFIDENCE,
    DEFAULT_INFERENCE_SIZE,
    DEFAULT_NUM_DETECTION_THREADS,
    DEFAULT_STRIDE,
)


@dataclass
class InferenceParams:
    """Parameters for model inference."""
    show: bool = False
    conf: float = DEFAULT_CONFIDENCE
    save: bool = False
    imgsz: int = DEFAULT_INFERENCE_SIZE
    device: Optional[str] = None
    half: bool = True
    batch_size: Optional[int] = None  # Optional batch size for batching frames
    batch_timeout_ms: Optional[int] = None  # Optional timeout for forming a batch

    @classmethod
    def from_dict(cls, params: dict) -> 'InferenceParams':
        """Create InferenceParams from dictionary."""
        return cls(
            show=params.get('show', False),
            conf=params.get('conf', DEFAULT_CONFIDENCE),
            save=params.get('save', False),
            imgsz=params.get('inference_size', params.get('imgsz', DEFAULT_INFERENCE_SIZE)),
            device=params.get('device', None),
            half=params.get('half', True),
            batch_size=params.get('batch_size', None),
            batch_timeout_ms=params.get('batch_timeout_ms', None),
        )

    def to_dict(self) -> dict:
        """Convert InferenceParams to dictionary."""
        return {
            'show': self.show,
            'conf': self.conf,
            'save': self.save,
            'imgsz': self.imgsz,
            'device': self.device,
            'half': self.half,
            'batch_size': self.batch_size,
            'batch_timeout_ms': self.batch_timeout_ms,
        }


@dataclass
class DetectorConfig:
    """Configuration for object detector."""
    stride: int = DEFAULT_STRIDE
    num_detection_threads: int = DEFAULT_NUM_DETECTION_THREADS
    inference_params: Optional[InferenceParams] = None

    @classmethod
    def from_dict(cls, params: dict) -> 'DetectorConfig':
        """Create DetectorConfig from dictionary."""
        return cls(
            stride=params.get('vid_stride', DEFAULT_STRIDE),
            num_detection_threads=params.get('num_detection_threads', DEFAULT_NUM_DETECTION_THREADS),
            inference_params=InferenceParams.from_dict(params),
        )
