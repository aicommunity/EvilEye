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


def test_collect_runtime_telemetry_uses_existing_module_instances_only():
    from evileye.controller.controller import Controller

    class Pipeline:
        def get_runtime_stats(self):
            stats = {"worker_running": True, "degraded": False}
            return {
                "modules": {"detectors/evileye/Rule": stats},
                "module_instances": {"detectors:0:evileye/Rule": stats},
                "stages": {"detectors": {"degraded": False}},
            }

    class Alarm:
        def get_runtime_stats(self):
            return {"worker_running": True, "degraded": False}

    class Events:
        def get_all_detectors(self):
            return {"Alarm": Alarm()}

    ctrl = Controller.__new__(Controller)
    ctrl.pipeline = Pipeline()
    ctrl.params = {"events_detectors": {"enabled": ["Alarm"], "Alarm": {}}}
    ctrl._events_service = Events()
    ctrl.events_detectors_controller = None

    telemetry = ctrl._collect_runtime_telemetry()

    assert telemetry["module_instances"]["detectors:0:evileye/Rule"]["worker_running"] is True
    assert telemetry["module_instances"]["events:0:Alarm"]["worker_running"] is True
    assert telemetry["stages"]["detectors"]["degraded"] is False
    assert telemetry["degraded"] is False
