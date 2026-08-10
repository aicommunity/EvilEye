from __future__ import annotations

import os
from pathlib import Path

from evileye.core.paths import configs_dir, creds_path, runtime_dir, site_root


def test_site_root_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_SITE_DIR", str(tmp_path))
    assert site_root() == tmp_path.resolve()
    assert creds_path() == tmp_path.resolve() / "credentials.json"
    assert configs_dir() == tmp_path.resolve() / "configs"


def test_runtime_dir_not_literal_tmp(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    # tempfile.gettempdir may still use system temp; ensure path has evileye suffix
    path = runtime_dir()
    assert path.name == "evileye" or (path.parent / "evileye").exists() or "evileye" in str(path)
    assert "/tmp/evileye_mp_sessions" not in str(path)
