"""Shared BoTSORT configuration for thread and multiprocessing workers."""

from dataclasses import dataclass, fields


@dataclass
class BostSortCfg:
    appearance_thresh: float = 0.25
    gmc_method: str = "sparseOptFlow"
    match_thresh: float = 0.8
    new_track_thresh: float = 0.6
    proximity_thresh: float = 0.5
    track_buffer: int = 30
    track_high_thresh: float = 0.5
    track_low_thresh: float = 0.1
    tracker_type: str = "botsort"
    fuse_score: bool = True
    with_reid: bool = False


def botsort_cfg_from_dict(cfg_dict: dict) -> BostSortCfg:
    """Build config from a partial dict (unknown keys ignored)."""
    valid_fields = {f.name for f in fields(BostSortCfg)}
    filtered = {k: v for k, v in (cfg_dict or {}).items() if k in valid_fields}
    return BostSortCfg(**filtered)
