"""Load built-in plugin declarations for metadata-only CLI operations."""

from __future__ import annotations


def register_builtins() -> None:
    """Import built-in module manifests and pipeline declarations.

    Factories are registered but never constructed, so inspection and editing
    do not open cameras, load neural models, or start worker processes.
    """
    from .plugins import plugin_manager

    # Third-party entries are loaded first so an accidental collision with an
    # EvilEye builtin is reported by the normal registry validation path.
    plugin_manager.load()

    import evileye.capture  # noqa: F401
    import evileye.attributes_detection  # noqa: F401
    import evileye.object_multi_camera_tracker  # noqa: F401
    import evileye.object_tracker  # noqa: F401
    import evileye.preprocessing  # noqa: F401
    from evileye.object_detector import register_builtin_modules
    from evileye.events_detectors.event_registry import register_builtins as register_event_builtins
    from evileye.controller.services.pipeline_service import PipelineService

    register_builtin_modules()
    register_event_builtins()
    PipelineService._register_builtin_pipelines()
