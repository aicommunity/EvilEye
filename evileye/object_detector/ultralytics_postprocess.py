"""Post-load optimizations for Ultralytics models (same thread/process only)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional


def apply_ultralytics_optimizations(
        model: Any,
        *,
        half: bool = True,
        logger: Optional[logging.Logger] = None,
) -> None:
    """
    Apply fuse() and optional half() to a model already constructed via YOLO()/RTDETR().

    Must be called in the same OS thread/process that created the model.
    """
    log = logger
    try:
        model.fuse()
    except Exception as e:
        if log is not None:
            log.debug("Model fuse() failed (non-critical): %s", e)
    if half:
        try:
            model.half()
        except Exception as e:
            if log is not None:
                log.warning("Failed to apply half precision (non-critical): %s", e)


def build_class_mapping_from_names(names: Optional[Dict]) -> Optional[Dict[str, int]]:
    """Build {class_name: class_id} from model.names."""
    if not names:
        return None
    return {name: idx for idx, name in names.items()}
