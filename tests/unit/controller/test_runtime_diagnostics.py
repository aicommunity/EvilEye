import json

from evileye.api.core import control_ipc
from evileye.controller.controller import Controller


class _Stats:
    def __init__(self, value):
        self.value = value

    def get_runtime_stats(self):
        return self.value


def _controller():
    ctrl = Controller.__new__(Controller)
    ctrl.pipeline = _Stats({"degraded": False, "modules": {"detector/test": {"worker_running": True}}})
    ctrl.obj_handler = None
    ctrl.events_detectors_controller = _Stats(
        {"degraded": True, "detector_failures": {"event/test": 1}}
    )
    ctrl.events_processor = _Stats({"degraded": False, "queue_rejections": 0})
    ctrl.event_buffers = {4: _Stats({"degraded": False, "queued": 2})}
    return ctrl


def test_runtime_stats_control_command_aggregates_pipeline_and_event_health():
    result = _controller()._handle_control_command({"cmd": "get_runtime_stats"})

    assert result["ok"] is True
    assert result["stats"]["available"] is True
    assert result["stats"]["degraded"] is True
    assert result["stats"]["components"]["pipeline"]["modules"]["detector/test"]["worker_running"] is True
    assert result["stats"]["components"]["events_controller"]["detector_failures"] == {"event/test": 1}
    assert result["stats"]["components"]["event_buffers"]["4"]["queued"] == 2
    json.dumps(result)


def test_runtime_stats_control_command_reports_provider_failure_as_degraded():
    ctrl = Controller.__new__(Controller)

    class _Broken:
        def get_runtime_stats(self):
            raise RuntimeError("stats failed")

    ctrl.pipeline = _Broken()
    ctrl.obj_handler = None
    ctrl.events_detectors_controller = None
    ctrl.events_processor = None
    ctrl.event_buffers = {}

    result = ctrl._handle_control_command({"cmd": "get_runtime_stats"})

    assert result["ok"] is True
    assert result["stats"]["degraded"] is True
    assert result["stats"]["components"]["pipeline"] == {
        "degraded": True,
        "diagnostic_error": "stats failed",
    }


def test_runtime_stats_control_command_round_trips_over_control_ipc(monkeypatch, tmp_path):
    socket_path = tmp_path / "control.sock"
    monkeypatch.setattr(control_ipc, "control_socket_path", lambda: socket_path)
    server = control_ipc.ControlIpcServer()
    server.start(_controller()._handle_control_command)
    try:
        response = control_ipc.send_control_command({"cmd": "get_runtime_stats"}, timeout=2.0)
    finally:
        server.stop()

    assert response["ok"] is True
    assert response["stats"]["degraded"] is True
    assert response["stats"]["components"]["events_processor"]["queue_rejections"] == 0
