from evileye.core.mp_control import MpControl


def test_mp_control_metrics_snapshot():
    ctrl = MpControl(max_input_size=2, max_output_size=2, name="test-metrics")
    ctrl.put_nowait({"x": 1})
    metrics = ctrl.get_metrics()
    assert "put_calls_total" in metrics
    assert "worker_restart_total" in metrics
    assert "restart_suppressed_total" in metrics
    assert "avg_put_wait_ms" in metrics
    assert metrics["input_queue_size"] >= 1
