"""Controller periodic runtime snapshot refresh for process-mode capture health."""

from evileye.controller.controller import Controller


class _SyncSpy:
    def __init__(self):
        self.calls = 0

    def sync_process_mode_health(self):
        self.calls += 1


def test_sync_capture_health_for_snapshot_calls_sources():
    ctrl = Controller.__new__(Controller)
    spy = _SyncSpy()
    ctrl._pipeline_service = type(
        "PS",
        (),
        {"get_sources": lambda self: [spy]},
    )()
    ctrl.pipeline = None
    ctrl._sync_capture_health_for_snapshot()
    assert spy.calls == 1


def test_maybe_publish_runtime_snapshot_respects_interval():
    ctrl = Controller.__new__(Controller)
    ctrl.run_flag = True
    ctrl._runtime_snapshot_every_sec = 10.0
    ctrl._runtime_snapshot_last_ts = 100.0
    ctrl._sync_capture_health_for_snapshot = lambda: None
    published = []
    ctrl._publish_runtime_snapshot = lambda **kwargs: published.append(kwargs)
    ctrl._maybe_publish_runtime_snapshot(now_ts=105.0)
    assert published == []
    ctrl._maybe_publish_runtime_snapshot(now_ts=110.0)
    assert len(published) == 1
    assert published[0]["state"] == "running"
