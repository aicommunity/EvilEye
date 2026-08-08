import pytest
from multiprocessing import Event

from evileye.capture.mp_worker_capture import (
    CAPTURE_INIT_FAIL_EXIT_CODE,
    MpWorkerCapture,
)
from evileye.core.mp_control import parse_mp_restart_policy


def test_capture_init_fail_exit_code_in_no_restart_defaults():
    restart, codes = parse_mp_restart_policy(
        {},
        default_restart_on_exit=False,
        default_no_restart_exit_codes={CAPTURE_INIT_FAIL_EXIT_CODE, -15},
    )
    assert restart is False
    assert CAPTURE_INIT_FAIL_EXIT_CODE in codes


def test_call_exits_with_init_fail_code_when_capture_none(monkeypatch):
    worker = MpWorkerCapture(None, None, stop_event=Event())
    monkeypatch.setattr(worker, "_init_logger", lambda: None)
    monkeypatch.setattr(worker, "init_worker", lambda: None)
    worker._capture = None

    with pytest.raises(SystemExit) as exc_info:
        worker()
    assert exc_info.value.code == CAPTURE_INIT_FAIL_EXIT_CODE


def test_call_exits_with_init_fail_code_on_exception(monkeypatch):
    worker = MpWorkerCapture(None, None, stop_event=Event())
    monkeypatch.setattr(worker, "_init_logger", lambda: None)

    def boom():
        raise RuntimeError("init failed")

    monkeypatch.setattr(worker, "init_worker", boom)

    with pytest.raises(SystemExit) as exc_info:
        worker()
    assert exc_info.value.code == CAPTURE_INIT_FAIL_EXIT_CODE
