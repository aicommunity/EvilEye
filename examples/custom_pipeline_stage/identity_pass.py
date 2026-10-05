"""Minimal custom pipeline stage — IdentityPass (pass-through DualModeProcessor).

Usage (from repo root)::

    # 1. Copy this module onto PYTHONPATH or keep under examples/
    # 2. Put pipelines/my_identity_pipeline.py in CWD (see sibling file)
    # 3. Run:
    #    PYTHONPATH=examples/custom_pipeline_stage:$PYTHONPATH \\
    #      evileye run examples/custom_pipeline_stage/config_declarative.json --no-gui

Register with ``@EvilEyeBase.register`` and list ``"type": "IdentityPass"``
in a PipelineDeclarative stage — no Controller / Surveillance fork required.
"""

from __future__ import annotations

import threading
from queue import Empty, Queue

from evileye.core.base_class import EvilEyeBase
from evileye.core.dual_mode_processor import DualModeProcessor
from evileye.core.processor_base import EXEC_MODE_THREAD


@EvilEyeBase.register("IdentityPass")
class IdentityPass(DualModeProcessor):
    """Pass (data, frame) through unchanged — template for a custom step."""

    def __init__(self):
        super().__init__()
        self.execution_mode = EXEC_MODE_THREAD
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue(maxsize=4)
        self.run_flag = False
        self.processing_thread = None
        self.source_ids: list[int] = []

    def set_params_impl(self):
        super().set_params_impl()
        self.source_ids = list(self.params.get("source_ids") or [])

    def get_params_impl(self):
        return {
            "source_ids": self.source_ids,
            "execution_mode": self.execution_mode,
        }

    def _init_thread_mode(self, **kwargs):
        self.processing_thread = threading.Thread(target=self._loop, daemon=True)
        return True

    def _init_process_mode(self, **kwargs):
        # Identity has no GPU work — keep thread.
        self.execution_mode = EXEC_MODE_THREAD
        return self._init_thread_mode(**kwargs)

    def start(self):
        self.run_flag = True
        if self.processing_thread and not self.processing_thread.is_alive():
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        try:
            self.queue_in.put_nowait(None)
        except Exception:
            pass
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1.0)

    def put(self, item, force=False):
        try:
            self.queue_in.put_nowait(item)
        except Exception:
            try:
                self.queue_in.get_nowait()
            except Exception:
                pass
            try:
                self.queue_in.put_nowait(item)
            except Exception:
                pass

    def get(self):
        try:
            return self.queue_out.get_nowait()
        except Empty:
            return None

    def get_source_ids(self):
        return self.source_ids

    def is_ready(self):
        return True

    def _loop(self):
        while self.run_flag:
            try:
                item = self.queue_in.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                break
            try:
                self.queue_out.put_nowait(item)
            except Exception:
                try:
                    self.queue_out.get_nowait()
                except Exception:
                    pass
                try:
                    self.queue_out.put_nowait(item)
                except Exception:
                    pass
