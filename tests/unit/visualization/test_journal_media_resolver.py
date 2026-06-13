from __future__ import annotations

from pathlib import Path

from evileye.visualization_modules.journal_media_resolver import (
    enrich_grouped_row,
    relative_to_base,
    resolve_event_video_path,
    resolve_stream_segment_path,
    row_key,
)


def test_row_key_stable():
    row = {"time": "2026-06-13T10:00:00", "event": "ZoneEvent", "information": "obj=1"}
    assert row_key(row) == "2026-06-13T10:00:00|ZoneEvent|obj=1"


def test_relative_to_base(tmp_path):
    base = tmp_path / "EvilEyeData"
    base.mkdir()
    video = base / "Events" / "2026-06-13" / "Videos" / "Cam1" / "clip.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x" * 2000)
    rel = relative_to_base(str(video), str(base))
    assert rel == str(Path("Events/2026-06-13/Videos/Cam1/clip.mp4"))


def test_resolve_event_video_from_db_path(tmp_path):
    base = tmp_path / "EvilEyeData"
    rel = "Events/2026-06-13/Videos/Cam1/Cam1_ZoneEvent_1_20260613_120000.mp4"
    full = base / rel
    full.parent.mkdir(parents=True)
    full.write_bytes(b"x" * 2000)
    event = {
        "event_type": "zone_entered",
        "ts": "2026-06-13T12:00:00",
        "source_name": "Cam1",
        "video_path": rel,
    }
    resolved = resolve_event_video_path(event, str(base))
    assert resolved == str(full)


def test_resolve_event_video_rejects_small_file(tmp_path):
    base = tmp_path / "EvilEyeData"
    rel = "Events/2026-06-13/Videos/Cam1/small.mp4"
    full = base / rel
    full.parent.mkdir(parents=True)
    full.write_bytes(b"x")
    event = {"event_type": "zone_entered", "ts": "2026-06-13T12:00:00", "video_path": rel}
    assert resolve_event_video_path(event, str(base)) is None


def test_resolve_stream_segment_closest(tmp_path):
    base = tmp_path / "EvilEyeData"
    segment_dir = base / "Streams" / "2026-06-13" / "Cam1"
    segment_dir.mkdir(parents=True)
    segment = segment_dir / "Cam1_20260613_120000_000001.mp4"
    segment.write_bytes(b"x" * 2000)
    event = {
        "ts": "2026-06-13T12:01:30",
        "source_name": "Cam1",
        "source_id": 0,
    }
    path, offset = resolve_stream_segment_path(event, str(base))
    assert path == str(segment)
    assert offset == 90


def test_enrich_grouped_row_adds_flags(tmp_path):
    base = tmp_path / "EvilEyeData"
    preview_dir = base / "Detections" / "2026-06-13" / "Images" / "FoundPreviews"
    preview_dir.mkdir(parents=True)
    preview_file = preview_dir / "obj_preview.jpg"
    preview_file.write_bytes(b"\xff\xd8\xff" + b"x" * 100)

    row = {
        "time": "2026-06-13T10:00:00",
        "event": "ObjectEvent",
        "information": "Object Id=1",
        "source": "Cam1",
        "time_lost": "",
        "preview": "obj_preview.jpg",
        "lost_preview": "",
        "found_event": {
            "event_type": "found",
            "ts": "2026-06-13T10:00:00",
            "date_folder": "2026-06-13",
            "image_filename": "obj_preview.jpg",
            "bounding_box": [0.1, 0.1, 0.2, 0.2],
        },
        "lost_event": None,
    }
    enriched = enrich_grouped_row(row, base_dir=str(base), journal_type="objects")
    assert enriched["row_key"]
    assert enriched["date_folder"] == "2026-06-13"
    assert enriched["has_found_preview"] is True
    assert enriched["bbox_found"] == [0.1, 0.1, 0.2, 0.2]
