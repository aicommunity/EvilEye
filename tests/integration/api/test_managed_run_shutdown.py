from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from evileye.api.core.config_run_manager import (
    ConfigRunItem,
    ConfigRunManager,
    ConfigRunState,
)
from evileye.core.process_control import terminate_tree


pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="managed process-group shutdown contract is POSIX-specific",
)


def _wait_for_files(paths: tuple[Path, ...], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(path.exists() for path in paths):
            return True
        time.sleep(0.02)
    return all(path.exists() for path in paths)


def test_managed_run_stop_lets_pipeline_owner_stop_its_worker(tmp_path: Path):
    owner_script = tmp_path / "pipeline_owner.py"
    owner_script.write_text(
        textwrap.dedent(
            """
            import multiprocessing as mp
            import signal
            import sys
            import time
            from pathlib import Path

            root = Path(sys.argv[1])

            def worker(stop_event, output_dir):
                output = Path(output_dir)

                def on_direct_signal(signum, frame):
                    (output / "worker_signaled_directly").touch()

                signal.signal(signal.SIGTERM, on_direct_signal)
                (output / "worker_ready").touch()
                stop_event.wait()
                (output / "worker_closed_by_owner").touch()

            def main():
                context = mp.get_context("spawn")
                stop_event = context.Event()

                def on_owner_signal(signum, frame):
                    (root / "owner_received_sigterm").touch()
                    stop_event.set()

                signal.signal(signal.SIGTERM, on_owner_signal)
                child = context.Process(target=worker, args=(stop_event, str(root)))
                child.start()
                (root / "owner_ready").touch()
                while child.is_alive():
                    child.join(timeout=0.05)
                (root / "owner_closed").touch()
                return child.exitcode or 0

            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [sys.executable, str(owner_script), str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_files(
            (tmp_path / "owner_ready", tmp_path / "worker_ready")
        )

        manager = ConfigRunManager()
        item = ConfigRunItem(91001, "managed-shutdown-test", tmp_path / "test.json")
        item.pid = process.pid
        item.state = ConfigRunState.RUNNING
        manager._items[item.id] = item

        with patch(
            "evileye.api.core.process_restart.pid_hosts_current_process",
            return_value=False,
        ), patch("evileye.api.core.config_run_manager.mark_runtime_stopped"):
            manager._stop_grace_sec = lambda: 3.0  # type: ignore[method-assign]
            result = manager.stop(item.id)

        assert result["state"] == ConfigRunState.STOPPED
        assert process.wait(timeout=3.0) == 0
        assert (tmp_path / "owner_received_sigterm").exists()
        assert (tmp_path / "worker_closed_by_owner").exists()
        assert (tmp_path / "owner_closed").exists()
        assert not (tmp_path / "worker_signaled_directly").exists()
    finally:
        if process.poll() is None:
            terminate_tree(process.pid, grace_sec=0.2)
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
