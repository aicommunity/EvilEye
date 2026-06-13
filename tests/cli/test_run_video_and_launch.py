"""CLI contract tests for process --video and launch positional config."""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESS_SCRIPT = PROJECT_ROOT / "evileye" / "process.py"
LAUNCH_MODULE = "evileye.launch"


def test_process_parser_accepts_video_flag():
    result = subprocess.run(
        [sys.executable, str(PROCESS_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    assert result.returncode == 0
    assert "--video" in result.stdout


def test_launch_parser_accepts_config_positional():
    result = subprocess.run(
        [sys.executable, "-m", LAUNCH_MODULE, "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    assert result.returncode == 0
    assert "config" in result.stdout.lower()


@pytest.mark.unit
def test_config_path_for_video_uses_template(tmp_path):
    from evileye.process import _config_path_for_video
    import logging

    template = PROJECT_ROOT / "configs" / "single_video.json"
    if not template.is_file():
        pytest.skip("single_video.json template missing")

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    logger = logging.getLogger("test")
    out = _config_path_for_video(str(video), logger)
    assert Path(out).is_file()
    import json

    with open(out, encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["pipeline"]["sources"][0]["camera"] == str(video.resolve())
