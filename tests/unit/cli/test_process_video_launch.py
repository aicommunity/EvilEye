"""The video launch must execute the config generated for that video."""

import logging
from types import SimpleNamespace

import pytest


def test_video_launch_passes_generated_config_to_runtime(tmp_path, monkeypatch):
    from evileye import process

    generated = tmp_path / "generated-video.json"
    generated.write_text("{}", encoding="utf-8")
    args = SimpleNamespace(config=None, video="sample.mp4", gui=False, autoclose=True, log_level="INFO")
    monkeypatch.setattr(process, "create_args_parser", lambda: args)
    monkeypatch.setattr(process, "ensure_spawn_start_method", lambda: None)
    monkeypatch.setattr(process, "cleanup_stale_sessions", lambda: 0)
    monkeypatch.setattr(process, "setup_evileye_logging", lambda **_kwargs: logging.getLogger("video-launch-test"))
    monkeypatch.setattr(process, "log_system_info", lambda _logger: None)
    monkeypatch.setattr(process, "_config_path_for_video", lambda *_args: str(generated))
    monkeypatch.setenv("EVILEYE_PIPELINE_ID", "314")
    monkeypatch.setenv("EVILEYE_SITE_DIR", str(tmp_path))
    monkeypatch.setenv("EVILEYE_SESSION_ID", "video-launch-test")
    for name in ("register_runtime", "update_runtime_snapshot", "mark_runtime_stopped"):
        monkeypatch.setattr(process, name, lambda *_args, **_kwargs: None)
    calls = []
    monkeypatch.setattr(process, "run_config", lambda path, **options: calls.append((path, options)) or 0)

    with pytest.raises(SystemExit) as result:
        process.main()

    assert result.value.code == 0
    assert calls == [(str(generated.resolve()), {"gui": False, "autoclose": True})]
