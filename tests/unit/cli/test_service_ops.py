"""Unit tests for service control helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from evileye.service_manager import control_service


def test_control_service_not_installed(tmp_path: Path):
    with patch("evileye.service_manager.load_state", return_value={"installed": False}):
        result = control_service("start", site_dir=tmp_path)
    assert result.ok is False
    assert "not installed" in result.message.lower()
