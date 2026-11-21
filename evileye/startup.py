"""Early startup hooks for EvilEye console entry points."""

from __future__ import annotations

import os


def configure_third_party_quiet() -> None:
    """Reduce noisy third-party warnings before heavy optional imports."""
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    # ONNX Runtime uses C++ logging; must be set before the first import.
    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
