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


class ConfigEchoProcessor:
    def __init__(self, config):
        assert set(config) == {"threshold"}, "runtime envelope leaked into factory config"
        self.config = dict(config)

    def process_item(self, item, state):
        return dict(self.config)
