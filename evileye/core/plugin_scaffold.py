from __future__ import annotations

import keyword
import re
from pathlib import Path
from typing import Any


class PluginScaffoldError(ValueError):
    """Raised when a plugin scaffold cannot be created safely."""


_TEMPLATES: dict[str, dict[str, Any]] = {
    "processor": {
        "description": "Minimal item processor that annotates a payload.",
        "module_id": "example_processor",
        "module_file": "processor",
        "class_name": "ExampleProcessor",
        "kind": "processor_item",
        "execution_modes": ("thread", "process"),
        "default_mode": "thread",
        "capabilities": (),
        "config_schema": {"type": "object", "properties": {
            "label": {"type": "string", "default": "starter", "description": "Label appended to mapping payloads."},
        }, "additionalProperties": True},
        "module_source": '''
class ExampleProcessor:
    """Small item processor example; replace the sample transformation."""

    def __init__(self, config):
        self.label = str(config.get("label", "starter"))

    def create_state(self, config, context=None):
        return {"processed": 0}

    def process_item(self, item, state):
        state["processed"] += 1
        if isinstance(item, (list, tuple)) and len(item) == 2:
            data, frame = item
            if isinstance(data, dict):
                data = dict(data)
                data["plugin_label"] = self.label
            return [data, frame]
        if isinstance(item, dict):
            result = dict(item)
            result["plugin_label"] = self.label
            result["plugin_item_number"] = state["processed"]
            return result
        return {"value": item, "plugin_label": self.label}
''',
    },
    "detector": {
        "description": "Surveillance detector returning a DetectionResultList.",
        "module_id": "example_detector",
        "module_file": "detector",
        "class_name": "ExampleDetector",
        "kind": "processor_item",
        "execution_modes": ("thread", "process"),
        "default_mode": "thread",
        "capabilities": (),
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "module_source": '''
from evileye.object_detector import DetectionResultList


class ExampleDetector:
    """Valid detector output skeleton; add inference where marked below."""

    def __init__(self, config):
        self.config = dict(config)

    def create_state(self, config, context=None):
        return {"processed": 0}

    def process_item(self, item, state):
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        state["processed"] += 1

        detections = DetectionResultList()
        detections.source_id = frame.source_id
        detections.frame_id = frame.frame_id
        detections.time_stamp = frame.time_stamp

        # TODO: run your model and append DetectionResult instances.
        # bounding_box uses [x1, y1, x2, y2] source-frame pixel coordinates.
        return detections, frame
''',
    },
    "alarm": {
        "description": "Process-isolated EventUpdate rule producing generic alarms.",
        "module_id": "example_alarm",
        "module_file": "alarm",
        "class_name": "ExampleAlarmRule",
        "kind": "event_detector",
        "execution_modes": ("process",),
        "default_mode": "process",
        "capabilities": ("event_updates",),
        "config_schema": {"type": "object", "properties": {
            "required_attributes": {"type": "array", "items": {"type": "string"}, "default": ["helmet"], "description": "Attributes required for a person to pass the rule."},
        }, "additionalProperties": True},
        "module_source": '''
from evileye.events_detectors.alarm_event import AlarmEvent


class ExampleAlarmRule:
    """PPE rule example: alarm on the transition into a missing-attribute state."""

    def __init__(self, config):
        self.required_attributes = tuple(
            str(value) for value in config.get("required_attributes", ["helmet"])
        )

    def create_state(self, config, context=None):
        return {"active_violations": set()}

    def process_update(self, update, state):
        current_violations = set()
        alarms = []
        for obj in update.payload.get("active", []):
            attributes = obj.get("attributes") or {}
            present = {
                name
                for name, value in attributes.items()
                if isinstance(value, dict) and value.get("state") == "exists"
            }
            missing = tuple(sorted(set(self.required_attributes) - present))
            object_id = str(obj.get("object_id", obj.get("id", "")))
            if not missing or not object_id:
                continue

            violation = (update.source_id, object_id, missing)
            current_violations.add(violation)
            if violation in state["active_violations"]:
                continue

            alarms.append(
                AlarmEvent(
                    "ppe_violation",
                    severity="critical",
                    source_id=update.source_id,
                    details={"object_id": object_id, "missing": list(missing)},
                    alarm_id=(
                        f"ppe:{update.source_id}:{object_id}:"
                        f"{update.sequence}:{','.join(missing)}"
                    ),
                )
            )

        state["active_violations"] = current_violations
        return alarms
''',
    },
    "source": {
        "description": "Synthetic Frame source with open/read/close lifecycle.",
        "module_id": "synthetic_source",
        "module_file": "source",
        "class_name": "SyntheticSource",
        "kind": "source",
        "execution_modes": ("thread", "process"),
        "default_mode": "thread",
        "capabilities": (),
        "dependencies": ["numpy>=1.24"],
        "config_schema": {"type": "object", "properties": {
            "source_id": {"type": "integer", "default": 0, "minimum": 0},
            "width": {"type": "integer", "default": 640, "minimum": 1},
            "height": {"type": "integer", "default": 480, "minimum": 1},
            "max_frames": {"type": "integer", "default": 20, "minimum": 0},
            "interval_sec": {"type": "number", "default": 0.2, "minimum": 0},
        }, "additionalProperties": True},
        "module_source": '''
import time

import numpy as np

from evileye.core.frame import Frame


class SyntheticSource:
    """Finite black-frame source for exercising source lifecycle and wiring."""

    def __init__(self, config):
        self.source_id = int(config.get("source_id", 0))
        self.width = int(config.get("width", 640))
        self.height = int(config.get("height", 480))
        self.max_frames = int(config.get("max_frames", 20))
        self.interval_sec = max(0.0, float(config.get("interval_sec", 0.2)))
        self._frame_id = 0
        self._opened = False

    def open(self):
        self._frame_id = 0
        self._opened = True

    def read(self):
        if not self._opened:
            raise RuntimeError("call open() before read()")
        if self.max_frames > 0 and self._frame_id >= self.max_frames:
            return None
        if self.interval_sec:
            time.sleep(self.interval_sec)

        frame = Frame()
        frame.source_id = self.source_id
        frame.frame_id = self._frame_id
        frame.time_stamp = time.time()
        frame.image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._frame_id += 1
        return frame

    def close(self):
        self._opened = False
''',
    },
    "pipeline": {
        "description": "Custom IPipeline implementation registered by PipelineSpec.",
        "module_id": "example_pipeline",
        "module_file": "pipeline",
        "class_name": "ExamplePipeline",
        "kind": "pipeline",
        "execution_modes": (),
        "default_mode": None,
        "capabilities": (),
        "config_schema": {"type": "object", "properties": {
            "marker": {"type": "string", "default": "example", "description": "Value returned by the demonstration pipeline."},
        }, "additionalProperties": True},
        "module_source": '''
from evileye.core.pipeline_base import PipelineBase


class ExamplePipeline(PipelineBase):
    """Minimal custom pipeline lifecycle example."""

    def __init__(self, marker="example"):
        super().__init__()
        self.marker = str(marker)
        self.sequence = 0
        self.running = False
        self._sources = []

    def set_params_impl(self):
        self.marker = str(self.params.get("marker", self.marker))

    def get_params_impl(self):
        return {"pipeline_class": self.__class__.__name__, "marker": self.marker}

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def process(self):
        if not self.running:
            raise RuntimeError("start the pipeline before process()")
        self.sequence += 1
        result = {"marker": self.marker, "sequence": self.sequence}
        self._current_results = result
        self.add_result(result)
        return result

    def get_sources(self):
        return list(self._sources)

    def generate_default_structure(self, num_sources):
        return {"marker": self.marker, "source_count": int(num_sources)}
''',
    },
}


def template_names() -> tuple[str, ...]:
    return tuple(_TEMPLATES)


def template_descriptions() -> dict[str, str]:
    return {name: str(template["description"]) for name, template in _TEMPLATES.items()}


def template_module_id(template_name: str) -> str:
    return str(_TEMPLATES[template_name]["module_id"])


def normalize_plugin_name(name: str) -> tuple[str, str]:
    """Return (directory name, Python-safe plugin id) for a simple user name."""
    value = str(name or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", value):
        raise PluginScaffoldError(
            "name must start with a letter and contain only lowercase letters, "
            "digits, hyphens or underscores"
        )
    plugin_id = value.replace("-", "_")
    if keyword.iskeyword(plugin_id) or plugin_id == "evileye":
        raise PluginScaffoldError(f"'{name}' is reserved and cannot be used as a plugin name")
    return value, plugin_id


def _plugin_source(plugin_id: str, template_name: str, template: dict[str, Any]) -> str:
    module_id = str(template["module_id"])
    module_file = str(template["module_file"])
    class_name = str(template["class_name"])
    if template_name == "pipeline":
        body = f'''
from evileye.core.plugins import (
    PipelineSpec,
    PLUGIN_API_VERSION,
    PluginSpec,
)
from .{module_file} import {class_name}


def create_pipeline(dependencies):
    config = dependencies.config.raw_config
    return {class_name}(marker=config.get("marker", "example"))


def load_plugin():
    return PluginSpec(
        plugin_id="{plugin_id}",
        api_version=PLUGIN_API_VERSION,
        pipelines=(
            PipelineSpec(
                pipeline_id="{module_id}",
                factory=create_pipeline,
                config_schema={template["config_schema"]!r},
            ),
        ),
    )
'''
    else:
        modes = ", ".join(repr(mode) for mode in template["execution_modes"])
        capabilities = repr(tuple(template["capabilities"]))
        default_mode = template["default_mode"]
        default_line = (
            f'            default_execution_mode="{default_mode}",\n'
            if default_mode
            else ""
        )
        body = f'''
from evileye.core.plugins import (
    ModuleSpec,
    PLUGIN_API_VERSION,
    PluginSpec,
)
from .{module_file} import {class_name}


def load_plugin():
    return PluginSpec(
        plugin_id="{plugin_id}",
        api_version=PLUGIN_API_VERSION,
        modules=(
            ModuleSpec(
                module_id="{module_id}",
                kind="{template["kind"]}",
                factory={class_name},
                execution_modes=({modes},),
                capabilities={capabilities},
                config_schema={template["config_schema"]!r},
{default_line.rstrip()}
            ),
        ),
    )
'''
    return body.lstrip()


def _readme(plugin_id: str, template_name: str, template: dict[str, Any]) -> str:
    qualified_id = f'{plugin_id}/{template["module_id"]}'
    if template_name == "pipeline":
        usage = f'''
Configure the custom pipeline with this identifier:

    "pipeline_class": "{qualified_id}"

The example reads the marker from PipelineDependencies.config.raw_config.
'''
    elif template_name == "alarm":
        usage = f'''
Enable the detector in the events_detectors section. Keep any built-in detector
names you still need in the enabled list:

    "events_detectors": {{
      "enabled": ["CamEventsDetector", "{qualified_id}"],
      "{qualified_id}": {{
        "execution_mode": "process",
        "required_attributes": ["helmet", "vest"]
      }}
    }}

The rule emits a generic AlarmEvent on a transition into a violation state.
'''
    elif template_name == "detector":
        usage = f'''
Add the detector to PipelineSurveillance:

    "modules": {{
      "detectors": {{
        "mode": "extend",
        "items": [{{
          "module_id": "{qualified_id}",
          "source_ids": [0],
          "execution_mode": "thread"
        }}]
      }}
    }}

The template returns an empty DetectionResultList until inference is added.
'''
    elif template_name == "source":
        usage = f'''
This module is a finite synthetic source, intended for wiring and lifecycle
checks. It emits black BGR frames. Configure it through a sources module entry
with module_id "{qualified_id}" and the source settings accepted by
SyntheticSource.__init__.
'''
    else:
        usage = f'''
The module id is {qualified_id}. Add it to a PipelineSurveillance module group
that accepts processor_item modules, or adapt its item contract to the chosen
group. The sample appends a label to mapping payloads.
'''

    return f'''# Plugin {plugin_id}

Generated from EvilEye template: {template_name}

{template["description"]}

## Install for development

Use the same Python environment that runs EvilEye:

    python -m pip install --upgrade pip setuptools
    python -m pip install -e .

Restart EvilEye after installing the package or changing plugin code. The
package declares an entry point in pyproject.toml; EvilEye does not scan this
directory directly or reload Python modules while running.

## Configure

{usage}
See EvilEye docs/PLUGINS.md for the full SPI, configuration and runtime
contracts. Process mode runs plugin code with EvilEye's privileges; it is not a
security sandbox.
'''


def create_plugin_project(name: str, output_dir: Path, template_name: str) -> Path:
    """Create a complete single-plugin package under output_dir/name."""
    directory_name, plugin_id = normalize_plugin_name(name)
    template_name = str(template_name or "").strip().lower()
    if template_name not in _TEMPLATES:
        choices = ", ".join(_TEMPLATES)
        raise PluginScaffoldError(
            f"unknown template '{template_name}'; choose one of: {choices}"
        )

    output_dir = Path(output_dir).expanduser().resolve()
    destination = output_dir / directory_name
    if destination.exists():
        raise PluginScaffoldError(f"destination already exists: {destination}")

    template = _TEMPLATES[template_name]
    package_dir = destination / plugin_id
    dependencies = ["evileye>=0.0.16", *template.get("dependencies", [])]
    dependency_lines = "\n".join(f'    "{item}",' for item in dependencies)
    pyproject = f'''[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "evileye-plugin-{directory_name.replace("_", "-")}"
version = "0.1.0"
description = "{template["description"]}"
requires-python = ">=3.10"
dependencies = [
{dependency_lines}
]

[project.entry-points."evileye.plugins"]
{plugin_id} = "{plugin_id}.plugin:load_plugin"

[tool.setuptools]
packages = ["{plugin_id}"]
'''
    package_dir.mkdir(parents=True)
    try:
        (destination / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        (destination / "README.md").write_text(
            _readme(plugin_id, template_name, template), encoding="utf-8"
        )
        (package_dir / "__init__.py").write_text(
            '"""EvilEye third-party plugin package."""\n', encoding="utf-8"
        )
        (package_dir / "plugin.py").write_text(
            _plugin_source(plugin_id, template_name, template), encoding="utf-8"
        )
        (package_dir / f'{template["module_file"]}.py').write_text(
            str(template["module_source"]).lstrip(), encoding="utf-8"
        )
    except OSError:
        import shutil

        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination
