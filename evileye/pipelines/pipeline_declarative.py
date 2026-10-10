"""Declarative pipeline: build stages from JSON ``stages`` list.

Example config fragment::

    {
      "pipeline_class": "PipelineDeclarative",
      "stages": [
        {"name": "sources", "kind": "source", "items": [{"module_id": "evileye/VideoCaptureOpencv", ...}]},
        {"name": "detectors", "kind": "step", "items": [{"module_id": "evileye/ObjectDetectorYolo", ...}]},
        {"name": "trackers", "kind": "step", "items": [{"module_id": "evileye/ObjectTrackingBotsort", ...}]}
      ],
      "final_results": "trackers"
    }

Authors register processors through ``register_module`` or an
``evileye.plugins`` entry point and select them with ``items[].module_id``.
Legacy ``items[].type`` remains supported.
"""

from __future__ import annotations

from typing import Any, Dict, List

import evileye.attributes_detection  # noqa: F401 — register plugins
import evileye.object_multi_camera_tracker  # noqa: F401
import evileye.preprocessing  # noqa: F401

from evileye.core.pipeline_processors import PipelineProcessors
from evileye.core.processor_base import ProcessorBase
from evileye.core.processor_frame import ProcessorFrame
from evileye.core.processor_source import ProcessorSource
from evileye.core.processor_step import ProcessorStep


class PipelineDeclarative(PipelineProcessors):
    """Build an ordered processor chain from ``params['stages']``."""

    def init_impl(self, **kwargs):
        stages: List[Dict[str, Any]] = list(self.params.get("stages") or [])
        if not stages:
            # Fallback: accept Surveillance-shaped sections for migration.
            stages = self._stages_from_legacy_sections(self.params)

        order = 0
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            name = str(stage.get("name") or f"stage_{order}")
            kind = str(stage.get("kind") or "step").lower()
            items = stage.get("items") or []
            if not isinstance(items, list) or not items:
                continue
            default_type = {
                "source": "VideoCaptureOpencv",
                "frame": "PreprocessingPipeline",
                "step": "ObjectDetectorYolo",
            }.get(kind, "ObjectDetectorYolo")
            class_name = ProcessorBase.configured_module_id(items[0], default_type)
            class_names = [
                ProcessorBase.configured_module_id(it, class_name)
                for it in items
            ]
            if kind == "source":
                proc = ProcessorSource(
                    processor_name=name,
                    class_name=class_name,
                    num_processors=len(items),
                    order=order,
                    class_names=class_names,
                )
                # Merge credentials into source params (same as Surveillance).
                credentials = self._credentials if isinstance(self._credentials, dict) else {}
                creds_sources = credentials.get("sources", {}) if credentials else {}
                for i, src_params in enumerate(items):
                    if not isinstance(src_params, dict):
                        continue
                    camera_creds = creds_sources.get(src_params.get("camera"), None)
                    if camera_creds and (
                        not src_params.get("username") or not src_params.get("password")
                    ):
                        src_params["username"] = camera_creds.get(
                            "username", src_params.get("username")
                        )
                        src_params["password"] = camera_creds.get(
                            "password", src_params.get("password")
                        )
                proc.set_params(items)
                proc.init()
                self.sources_proc = proc
            elif kind == "frame":
                proc = ProcessorFrame(
                    processor_name=name,
                    class_name=class_name,
                    num_processors=len(items),
                    order=order,
                    class_names=class_names,
                )
                proc.set_params(items)
                proc.init()
            else:
                proc = ProcessorStep(
                    processor_name=name,
                    class_name=class_name,
                    num_processors=len(items),
                    order=order,
                    class_names=class_names,
                )
                proc.set_params(items)
                init_kwargs = {}
                if name in {"trackers", "mc_trackers"} and self.encoders:
                    init_kwargs["encoders"] = self.encoders
                proc.init(**init_kwargs)
            self._add_processor(proc)
            order += 1

        self._final_results_name = str(
            self.params.get("final_results")
            or (stages[-1].get("name") if stages else "sources")
            or "sources"
        )
        return True

    @staticmethod
    def _stages_from_legacy_sections(params: Dict[str, Any]) -> List[Dict[str, Any]]:
        mapping = [
            ("sources", "source"),
            ("preprocessors", "frame"),
            ("detectors", "step"),
            ("trackers", "step"),
            ("mc_trackers", "step"),
            ("attributes_roi", "step"),
            ("attributes_classifier", "step"),
        ]
        out: List[Dict[str, Any]] = []
        for name, kind in mapping:
            items = params.get(name) or []
            if isinstance(items, list) and items:
                out.append({"name": name, "kind": kind, "items": items})
        return out
