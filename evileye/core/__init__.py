"""Lightweight public API for the core package.

Public names are loaded on first access so importing a worker contract does not
initialize pipelines, GUI modules, or every builtin plugin in spawned processes.
"""

from importlib import import_module as _import_module

_EXPORTS = {
    "EvilEyeBase": (".base_class", "EvilEyeBase"),
    "CaptureImage": (".frame", "CaptureImage"),
    "Frame": (".frame", "Frame"),
    "ProcessorBase": (".processor_base", "ProcessorBase"),
    "ProcessorSource": (".processor_source", "ProcessorSource"),
    "ProcessorStep": (".processor_step", "ProcessorStep"),
    "ProcessorFrame": (".processor_frame", "ProcessorFrame"),
    "MpWorker": (".mp_worker", "MpWorker"),
    "MpControl": (".mp_control", "MpControl"),
    "ProcessManager": (".process_manager", "ProcessManager"),
    "get_process_manager": (".process_manager", "get_process_manager"),
    "PipelineProcessors": (".pipeline_processors", "PipelineProcessors"),
    "PipelineBase": (".pipeline_base", "PipelineBase"),
    "PipelineSimple": (".pipeline_simple", "PipelineSimple"),
    "IDatabaseAdapter": (".interfaces", "IDatabaseAdapter"),
    "IEventDetector": (".interfaces", "IEventDetector"),
    "IProcessEventDetector": (".interfaces", "IProcessEventDetector"),
    "IObjectHandler": (".interfaces", "IObjectHandler"),
    "IPipeline": (".interfaces", "IPipeline"),
    "IVisualizer": (".interfaces", "IVisualizer"),
    "ControllerContext": (".contracts", "ControllerContext"),
    "DatabaseConfig": (".contracts", "DatabaseConfig"),
    "DatabaseDependencies": (".contracts", "DatabaseDependencies"),
    "EventsConfig": (".contracts", "EventsConfig"),
    "EventsDependencies": (".contracts", "EventsDependencies"),
    "EventFrameSnapshot": (".contracts", "EventFrameSnapshot"),
    "EventUpdate": (".contracts", "EventUpdate"),
    "PipelineConfig": (".contracts", "PipelineConfig"),
    "PipelineDependencies": (".contracts", "PipelineDependencies"),
    "VisualizationConfig": (".contracts", "VisualizationConfig"),
    "VisualizationDependencies": (".contracts", "VisualizationDependencies"),
    "DatabaseFacade": (".facades", "DatabaseFacade"),
    "PipelineFacade": (".facades", "PipelineFacade"),
    "DIContainer": (".di_container", "DIContainer"),
    "DependencyRegistry": (".dependencies", "DependencyRegistry"),
    "DependencyDefinition": (".dependencies", "DependencyDefinition"),
    "get_registry": (".dependencies", "get_registry"),
    "register_dependency": (".dependencies", "register_dependency"),
    "ConfigValidator": (".config_validator", "ConfigValidator"),
    "ObjectPool": (".object_pool", "ObjectPool"),
    "get_frame_broker": (".runtime_services", "get_frame_broker"),
    "get_pipeline_manager": (".runtime_services", "get_pipeline_manager"),
    "PipelineSurveillance": (".pipeline_surveillance", "PipelineSurveillance"),
    "PipelineCapture": (".pipeline_capture", "PipelineCapture"),
    "PipelineDeclarative": (".pipeline_declarative", "PipelineDeclarative"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = _import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
