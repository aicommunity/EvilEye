import os
import yaml
from pathlib import Path
from types import SimpleNamespace

BOTSORT_CFG_PATH = str(Path(__file__).parent / 'botsort.yaml')


def read_cfg(path: str = BOTSORT_CFG_PATH) -> SimpleNamespace:    
    with open(path) as f:
        cfg = yaml.safe_load(f)

    cfg = SimpleNamespace(**cfg)
    return cfg