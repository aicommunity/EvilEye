from __future__ import annotations

from evileye.core.mp_session_registry import _registry_dir


def test_registry_dir_uses_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    path = _registry_dir()
    assert path == tmp_path / "evileye" / "mp_sessions"
    assert path.is_dir()
