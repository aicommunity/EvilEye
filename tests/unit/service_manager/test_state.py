from pathlib import Path

from evileye.service_manager.minimal_config import ensure_system_config, minimal_system_config
from evileye.service_manager.state import clear_state, is_installed, load_state, save_state


def test_minimal_system_config_scaffold():
    cfg = minimal_system_config()
    assert cfg["pipeline"]["pipeline_class"] == "PipelineSurveillance"
    assert cfg["pipeline"]["sources"] == []
    assert cfg["controller"]["use_database"] is False
    assert cfg["database"]["image_dir"] == ""
    assert cfg["server"]["enabled"] is True


def test_ensure_system_config_creates_once(tmp_path: Path):
    path = ensure_system_config(tmp_path)
    assert path.exists()
    assert path.name == "system.json"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace('"fps": 30', '"fps": 15'), encoding="utf-8")
    ensure_system_config(tmp_path)
    assert '"fps": 15' in path.read_text(encoding="utf-8")


def test_state_roundtrip(tmp_path: Path):
    assert not is_installed(tmp_path)
    save_state({"installed": True, "backend": "systemd-user"}, tmp_path)
    assert is_installed(tmp_path)
    assert load_state(tmp_path)["backend"] == "systemd-user"
    assert clear_state(tmp_path) is True
    assert not is_installed(tmp_path)
