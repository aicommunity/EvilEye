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

def test_forced_worker_termination_does_not_wait_for_queue_feeders(monkeypatch):
    import queue
    from types import SimpleNamespace

    import evileye.core.mp_control as mp_control_module

    class _TrackedQueue:
        def __init__(self):
            self.closed = False
            self.cancelled = False
            self.join_calls = 0

        def put_nowait(self, value):
            return None

        def get_nowait(self):
            raise queue.Empty

        def cancel_join_thread(self):
            self.cancelled = True

        def close(self):
            self.closed = True

        def join_thread(self):
            self.join_calls += 1

    class _QueueContext:
        def __init__(self):
            self.queues = []

        def Queue(self, maxsize=0):
            result = _TrackedQueue()
            self.queues.append(result)
            return result

    class _StopEvent:
        def set(self):
            return None

    class _WorkerProcess:
        pid = 12345

        def __init__(self):
            self.alive = True
            self.terminated = False

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True
            self.alive = False

        def kill(self):
            self.alive = False

    context = _QueueContext()
    monkeypatch.setattr(mp_control_module, "get_spawn_context", lambda: context)
    monkeypatch.setattr(mp_control_module, "unregister_worker_pid", lambda pid: None)
    control = MpControl(name="forced-stop-test")
    process = _WorkerProcess()
    control.processes = [process]
    control.workers_list = [SimpleNamespace(_stop_event=_StopEvent())]

    control.stop(timeout=0.01)

    assert process.terminated is True
    assert all(ipc_queue.cancelled for ipc_queue in context.queues)
    assert all(ipc_queue.closed for ipc_queue in context.queues)
    assert all(ipc_queue.join_calls == 0 for ipc_queue in context.queues)
