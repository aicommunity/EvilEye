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


def test_shutdown_all_joins_manager_threads_and_closes_queues():
    ctrl = MpControl(name="shutdown-test")
    ctrl.start()
    log_listener = ctrl._log_listener
    monitor = ctrl._monitor_thread
    assert log_listener is not None and log_listener.is_alive()
    assert monitor is not None and monitor.is_alive()

    MpControl.shutdown_all(timeout=1.0)

    assert not log_listener.is_alive()
    assert not monitor.is_alive()
    assert ctrl._released is True
