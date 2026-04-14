from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackingObjectDTO:
    track_id: int
    class_id: int
    confidence: float
    bbox_xyxy: list[float]
    global_id: int | None = None


@dataclass
class TrackingDTO:
    source_id: int | None = None
    frame_id: int | None = None
    payload_version: int = 1
    tracks: list[TrackingObjectDTO] = field(default_factory=list)


def ensure_tracking_result_list(payload):
    """
    Convert TrackingDTO-like payloads to TrackingResultList.
    Keeps legacy TrackingResultList unchanged.
    """
    try:
        from ..object_tracker.tracking_results import TrackingResultList, TrackingResult
    except Exception:
        return payload

    if hasattr(payload, "tracks") and not isinstance(payload, dict):
        # Legacy object with tracks already.
        return payload

    dto = None
    if isinstance(payload, dict) and "tracks" in payload:
        dto = payload
    elif hasattr(payload, "tracking_dto"):
        dto_obj = getattr(payload, "tracking_dto")
        if dto_obj is not None:
            dto = {
                "source_id": getattr(dto_obj, "source_id", None),
                "frame_id": getattr(dto_obj, "frame_id", None),
                "tracks": getattr(dto_obj, "tracks", []) or [],
            }
    if dto is None:
        return payload

    out = TrackingResultList()
    out.source_id = dto.get("source_id")
    out.frame_id = dto.get("frame_id")
    out.time_stamp = dto.get("time_stamp", None)
    for t in dto.get("tracks", []) or []:
        tr = TrackingResult()
        if isinstance(t, dict):
            tr.track_id = int(t.get("track_id", 0))
            tr.class_id = int(t.get("class_id", -1))
            tr.confidence = float(t.get("confidence", 0.0))
            tr.bounding_box = [float(x) for x in (t.get("bbox_xyxy", []) or [])]
            tr.tracking_data = {"global_id": t.get("global_id")}
        else:
            tr.track_id = int(getattr(t, "track_id", 0))
            tr.class_id = int(getattr(t, "class_id", -1))
            tr.confidence = float(getattr(t, "confidence", 0.0))
            tr.bounding_box = [float(x) for x in (getattr(t, "bbox_xyxy", []) or [])]
            tr.tracking_data = {"global_id": getattr(t, "global_id", None)}
        out.tracks.append(tr)
    return out
