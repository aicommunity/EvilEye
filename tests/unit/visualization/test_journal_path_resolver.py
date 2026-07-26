from __future__ import annotations

import os

from evileye.visualization_modules.journal_path_resolver import JournalPathResolver


def test_legacy_detected_frames_resolves_preview(tmp_path):
    base = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    preview_dir = base / "Detections" / date / "Images" / "FoundPreviews"
    preview_dir.mkdir(parents=True)
    preview_file = preview_dir / "cam1_20260613_133000_1_preview.jpeg"
    preview_file.write_bytes(b"preview")

    img_path = "detected_frames/cam1_20260613_133000_1_frame.jpeg"
    event_data = {"date_folder": date}
    resolved = JournalPathResolver.resolve_image_path(
        img_path,
        str(base),
        event_data=event_data,
        journal_type="objects",
    )
    assert resolved == str(preview_file)


def test_missing_preview_falls_back_to_frame(tmp_path):
    base = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    frame_dir = base / "Detections" / date / "Images" / "FoundFrames"
    frame_dir.mkdir(parents=True)
    frame_file = frame_dir / "cam1_20260613_133000_1_frame.jpeg"
    frame_file.write_bytes(b"frame")

    img_path = "detected_frames/cam1_20260613_133000_1_frame.jpeg"
    event_data = {"date_folder": date}
    resolved = JournalPathResolver.resolve_image_path(
        img_path,
        str(base),
        event_data=event_data,
        journal_type="objects",
    )
    assert resolved == str(frame_file)


def test_found_previews_metadata_path_resolves(tmp_path):
    base = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    preview_dir = base / "Detections" / date / "Images" / "FoundPreviews"
    preview_dir.mkdir(parents=True)
    preview_file = preview_dir / "obj_preview.jpeg"
    preview_file.write_bytes(b"preview")

    img_path = os.path.join("Detections", date, "Images", "FoundPreviews", "obj_preview.jpeg")
    resolved = JournalPathResolver.resolve_image_path(
        img_path,
        str(base),
        event_data={"date_folder": date},
        journal_type="objects",
    )
    assert resolved == str(preview_file)
