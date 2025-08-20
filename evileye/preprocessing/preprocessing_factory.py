import json
import importlib
from preprocessing import steps


class PreprocessingFactory:
    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            config = json.load(f)
        self.pipeline_config = config["preprocessors"][0]["pipeline"]

    def build_pipeline(self):
        next_step = None
        for step_cfg in reversed(self.pipeline_config):
            class_name = step_cfg["name"]
            params = step_cfg.get("params", {})

            step_class = getattr(steps, class_name)
            next_step = step_class(aNextStep=next_step, **params)

        return next_step
