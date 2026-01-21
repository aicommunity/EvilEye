from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from evileye.core.logger import get_module_logger

from . import steps
from .steps.step_abstract import StepAbstract


class PreprocessingFactory:
    """Создает последовательность шагов препроцессинга из JSON-конфига."""

    def __init__(self, json_path: str):
        self.logger = get_module_logger(__name__)
        self.json_path = json_path
        self.pipeline_config: List[Dict[str, Any]] = []
        self._load_config()

    def _load_config(self) -> None:
        try:
            with open(self.json_path, "r") as f:
                config = json.load(f)
            sequence = config.get("preprocessing_sequence", [])
            if not isinstance(sequence, list):
                self.logger.error("preprocessing_sequence must be a list; got %s", type(sequence))
                sequence = []
            self.pipeline_config = sequence
        except Exception as ex:
            self.logger.error("Failed to load preprocessing pipeline from %s: %s", self.json_path, ex)
            self.pipeline_config = []

    def build_pipeline(self) -> Optional[StepAbstract]:
        next_step: Optional[StepAbstract] = None
        for step_cfg in reversed(self.pipeline_config):
            class_name = step_cfg.get("name")
            if not class_name:
                self.logger.error("Preprocessing step config missing 'name': %s", step_cfg)
                continue

            params = step_cfg.get("params", {}) or {}

            try:
                step_class = getattr(steps, class_name)
            except AttributeError:
                self.logger.error("Preprocessing step '%s' not found in steps module", class_name)
                continue

            try:
                next_step = step_class(next_step=next_step, **params)
            except Exception as ex:
                self.logger.error("Failed to create preprocessing step '%s': %s", class_name, ex)
                continue

        return next_step
