"""YOLO must be constructed only inside MpWorkerYolo child process."""

import multiprocessing as mp
import os
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest


def _child_init_and_report(result_queue, model_name: str):
    import os as _os

    from evileye.object_detector.mp_worker_yolo import MpWorkerYolo

    class _FakeYOLO:
        def __init__(self, path):
            self.path = path

        def fuse(self):
            pass

        def half(self):
            pass

    with patch("evileye.object_detector.mp_worker_yolo.YOLO", _FakeYOLO):
        worker = MpWorkerYolo(Queue(), Queue())
        worker.set_params(model_name, [0], {"half": False})
        worker.init_worker()
        result_queue.put((_os.getpid(), worker.model is not None, getattr(worker.model, "path", None)))


@pytest.mark.unit
def test_mp_worker_yolo_init_runs_in_child_process_only():
    parent_pid = os.getpid()
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    proc = ctx.Process(
        target=_child_init_and_report,
        args=(result_queue, "model.pt"),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0, f"child exit code {proc.exitcode}"

    child_pid, loaded, model_path = result_queue.get(timeout=5)
    assert child_pid != parent_pid
    assert loaded is True
    assert model_path == "model.pt"
