"""Spawn entry must not pickle worker instances with locks."""

import multiprocessing as mp

import pytest

from evileye.core.mp_context import get_spawn_context
from evileye.core.mp_control import MpControl
from evileye.core.mp_worker import MpWorker


class _EchoWorker(MpWorker):
    def __init__(self, input_queue, output_queue, log_queue=None, stop_event=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue, stop_event=stop_event)
        self.multiplier = 1

    def set_params(self, multiplier: int):
        self.multiplier = multiplier

    def get_spawn_state(self):
        return {"multiplier": self.multiplier}

    def apply_spawn_state(self, state):
        self.set_params(state.get("multiplier", 1))

    def init_worker(self):
        pass

    def worker_impl(self, data):
        return data * self.multiplier


@pytest.mark.unit
def test_mp_control_spawn_starts_worker_without_pickle_error():
    get_spawn_context()
    ctrl = MpControl(max_input_size=2, max_output_size=2, name="spawn-echo")
    worker = ctrl.add_worker(_EchoWorker)
    worker.set_params(3)
    ctrl.start()
    try:
        ctrl.put(2)
        assert ctrl.get(timeout=15) == 6
    finally:
        ctrl.stop(timeout=3)
