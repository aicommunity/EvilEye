from pathlib import Path

from evileye.utils.database_config_utils import resolve_writable_image_dir


def test_resolve_writable_image_dir_keeps_writable(tmp_path):
    chosen = resolve_writable_image_dir(str(tmp_path))
    assert Path(chosen) == tmp_path.resolve()


def test_resolve_writable_image_dir_falls_back(tmp_path, monkeypatch):
    bad = tmp_path / "missing_parent" / "nope"
    # Parent that cannot be created: use a file as parent path
    blocker = tmp_path / "blocker_file"
    blocker.write_text("x", encoding="utf-8")
    unwritable = blocker / "child"

    fallback = tmp_path / "EvilEyeData"
    monkeypatch.delenv("EVILEYE_DATA_DIR", raising=False)
    chosen = resolve_writable_image_dir(str(unwritable), fallback=str(fallback))
    assert Path(chosen) == fallback.resolve()
    assert fallback.is_dir()
