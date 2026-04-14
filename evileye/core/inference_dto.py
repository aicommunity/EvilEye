from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InferenceObjectDTO:
    bbox_xyxy: list[float]
    confidence: float
    class_id: int


@dataclass
class InferenceDTO:
    source_id: int | None = None
    frame_id: int | None = None
    time_stamp: float | None = None
    detections: list[InferenceObjectDTO] = field(default_factory=list)

    @classmethod
    def from_detector_payload(
        cls, payload: list[dict[str, Any]], source_id: int | None, frame_id: int | None
    ) -> "InferenceDTO":
        detections: list[InferenceObjectDTO] = []
        for item in payload or []:
            try:
                detections.append(
                    InferenceObjectDTO(
                        bbox_xyxy=[float(x) for x in item.get("bbox_xyxy", [])],
                        confidence=float(item.get("confidence", 0.0)),
                        class_id=int(item.get("class_id", -1)),
                    )
                )
            except Exception:
                continue
        return cls(source_id=source_id, frame_id=frame_id, detections=detections)
