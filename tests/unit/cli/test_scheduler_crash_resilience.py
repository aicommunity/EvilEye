"""Scheduler should auto-restart on crash but stop on graceful exit."""


def scheduler_should_continue(retcode: int, before_next_run: bool) -> bool:
    """Mirror of evileye.cli._run_with_scheduler child-exit policy."""
    if retcode == 2:
        return True
    if retcode == 0 and before_next_run:
        return False
    if retcode != 0 and before_next_run:
        return True
    return True


def test_graceful_exit_stops_scheduler() -> None:
    assert scheduler_should_continue(0, before_next_run=True) is False


def test_sigkill_auto_restarts() -> None:
    assert scheduler_should_continue(-9, before_next_run=True) is True


def test_sigsegv_auto_restarts() -> None:
    assert scheduler_should_continue(-11, before_next_run=True) is True


def test_memory_leak_restarts() -> None:
    assert scheduler_should_continue(2, before_next_run=True) is True


def test_exit_after_next_run_continues() -> None:
    assert scheduler_should_continue(0, before_next_run=False) is True
