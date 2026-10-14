"""Compatibility exports for the shared plugin scaffold service."""

from evileye.core.plugin_scaffold import (
    PluginScaffoldError,
    create_plugin_project,
    normalize_plugin_name,
    template_descriptions,
    template_module_id,
    template_names,
)

__all__ = [
    "PluginScaffoldError",
    "create_plugin_project",
    "normalize_plugin_name",
    "template_descriptions",
    "template_module_id",
    "template_names",
]
