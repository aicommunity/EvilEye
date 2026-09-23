"""A05: pytest must return non-zero when a test fails (no forced exit 0)."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_failing_test_returns_nonzero_exit(tmp_path: Path):
    probe = tmp_path / "probe_fail.py"
    probe.write_text(
        textwrap.dedent(
            """\
            def test_intentional_fail():
                assert False, "intentional failure for A05"
            """
        ),
        encoding="utf-8",
    )
    # Do not set EVILEYE_PYTEST_FORCE_EXIT — default path must preserve exitstatus.
    env = {k: v for k, v in __import__("os").environ.items()}
    env.pop("EVILEYE_PYTEST_FORCE_EXIT", None)
    env.pop("EVILEYE_PYTEST_NO_FORCE_EXIT", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-q", "--tb=no"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0, (
        f"expected non-zero exit on failure, got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_conftest_has_no_force_exit_zero():
    """Static guard: unconfigure must not call os._exit(0)."""
    conftest = Path(__file__).resolve().parents[2] / "conftest.py"
    text = conftest.read_text(encoding="utf-8")
    assert "os._exit(0)" not in text
    # At most one pytest_sessionfinish definition
    assert text.count("def pytest_sessionfinish") == 1
