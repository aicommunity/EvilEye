from __future__ import annotations

import threading

from evileye.visualization_modules.journal_init_thread import JournalInitThread


class _BlockingJournalThread(JournalInitThread):
    def __init__(self):
        super().__init__({}, {})
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self):
        self.started.set()
        self.release.wait(timeout=5)


def test_worker_remains_registered_until_native_thread_is_joined():
    worker = _BlockingJournalThread()
    worker.start()
    try:
        assert worker.started.wait(timeout=2)
        with JournalInitThread._instances_lock:
            assert worker in JournalInitThread._instances

        worker.release.set()
        assert worker.wait(2000)

        # run() has returned, but shutdown_all owns registry cleanup after
        # observing the QThread's completed state.
        with JournalInitThread._instances_lock:
            assert worker in JournalInitThread._instances
    finally:
        worker.release.set()
        JournalInitThread.shutdown_all(timeout_ms=2000)

    with JournalInitThread._instances_lock:
        assert worker not in JournalInitThread._instances
