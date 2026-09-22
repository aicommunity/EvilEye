"""Archive /journals/frame must serve full frames, never tiny previews."""

from __future__ import annotations

from pathlib import Path

import pytest

from evileye.api.core import journal_service


@pytest.fixture
def image_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "EvilEyeData"
    monkeypatch.setattr(journal_service, "_image_base_dir", lambda: str(base))
    journal_service._image_base_dir_cache = None
    return base


def test_frame_path_prefers_found_frames(image_base: Path):
    date = "2026-09-08"
    preview_dir = image_base / "Detections" / date / "Images" / "FoundPreviews"
    frame_dir = image_base / "Detections" / date / "Images" / "FoundFrames"
    preview_dir.mkdir(parents=True)
    frame_dir.mkdir(parents=True)
    name = "obj_Cam1"
    (preview_dir / f"{name}_preview.jpeg").write_bytes(b"tiny")
    frame = frame_dir / f"{name}_frame.jpeg"
    frame.write_bytes(b"full-res")

    resolved = journal_service.resolve_journal_frame_path(
        path=f"FoundPreviews/{name}_preview.jpeg",
        date=date,
        journal_type="objects",
        mode="found",
    )
    assert resolved == str(frame)


def test_frame_path_does_not_fallback_to_preview(image_base: Path):
    date = "2026-09-08"
    preview_dir = image_base / "Detections" / date / "Images" / "FoundPreviews"
    preview_dir.mkdir(parents=True)
    (preview_dir / "only_preview.jpeg").write_bytes(b"tiny")
    # No FoundFrames sibling.

    resolved = journal_service.resolve_journal_frame_path(
        path="FoundPreviews/only_preview.jpeg",
        date=date,
        journal_type="objects",
        mode="found",
    )
    assert resolved is None
