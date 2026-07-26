import multiprocessing as mp
import time

import pytest

from evileye.core.gpu_errors import MP_EXIT_CUDA_OOM
from evileye.core.mp_context import get_spawn_context
from evileye.core.mp_control import MpControl
from evileye.core.mp_worker import MpWorker


class _FatalOomWorker(MpWorker):
    def init_worker(self):
        raise RuntimeError("CUDA error: out of memory")

    def worker_impl(self, data):
        return data


@pytest.mark.unit
def test_mp_control_suppresses_restart_on_fatal_cuda_exit_code():
    get_spawn_context()
    fatal_calls = []

    def on_fatal(slot_index, exit_code, pool_name):
        fatal_calls.append((slot_index, exit_code, pool_name))

    ctrl = MpControl(
        max_input_size=2,
        max_output_size=2,
        name="fatal-oom-test",
        restart_on_exit=True,
        on_worker_fatal_exit=on_fatal,
    )
    ctrl.add_worker(_FatalOomWorker)
    ctrl.start()
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if ctrl._fatal_shutdown and not ctrl.is_operational():
                break
            time.sleep(0.1)
        assert ctrl._fatal_shutdown is True
        assert ctrl.is_operational() is False
        assert ctrl.restart_on_exit is False
        assert len(fatal_calls) == 1
        assert fatal_calls[0][1] == MP_EXIT_CUDA_OOM
        restarts = ctrl.get_metrics().get("worker_restart_total", 0)
        assert restarts == 0
    finally:
        ctrl.stop(timeout=3)
