"""Lightweight factories imported by spawned detector contract workers."""

import time


class NamedDetector:
    def __init__(self, config=None):
        self.name = (config or {}).get("name", "unnamed")
        self.delay_sec = float((config or {}).get("delay_sec", 0))
        self.return_none = bool((config or {}).get("return_none", False))

    def process_item(self, item, state):
        if self.delay_sec:
            time.sleep(self.delay_sec)
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        if self.return_none:
            return None
        return [{"detections": [{"label": self.name}]}, frame]


class ClassedDetector:
    """Returns one detection whose ``class_id`` is the model-local id from the config."""

    def __init__(self, config=None):
        self.name = (config or {}).get("name", "unnamed")
        self.local_class_id = int((config or {}).get("class_id", 0))
        self.model_class_mapping = dict((config or {}).get("mapping") or {})

    def get_model_class_mapping(self):
        return dict(self.model_class_mapping) or None

    def process_item(self, item, state):
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        return [
            {"detections": [{"label": self.name, "class_id": self.local_class_id}]},
            frame,
        ]


class ConfigEchoProcessor:
    def __init__(self, config):
        assert set(config) == {"threshold"}, "runtime envelope leaked into factory config"
        self.config = dict(config)

    def process_item(self, item, state):
        return dict(self.config)
