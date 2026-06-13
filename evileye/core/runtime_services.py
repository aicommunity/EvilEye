from __future__ import annotations

from typing import TYPE_CHECKING

from .runtime_context import get_or_create_runtime_service

if TYPE_CHECKING:
    from evileye.api.core.frame_broker import FrameBroker
    from evileye.api.core.pipeline_manager import PipelineManager


def _create_frame_broker():
    from evileye.api.core.frame_broker import FrameBroker

    return FrameBroker()


def _create_pipeline_manager():
    from evileye.api.core.pipeline_manager import PipelineManager

    return PipelineManager()


def get_frame_broker() -> "FrameBroker":
    return get_or_create_runtime_service("broker", _create_frame_broker)


def get_pipeline_manager() -> "PipelineManager":
    return get_or_create_runtime_service("manager", _create_pipeline_manager)
