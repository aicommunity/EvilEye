from __future__ import annotations

import time
from pathlib import Path

from evileye.api.core.ip_ban_store import IpBanStore, reset_ip_ban_store_for_tests


def test_prune_expired_does_not_rewrite_unchanged_file(tmp_path: Path) -> None:
    store_path = tmp_path / "web_ip_bans.json"
    store = reset_ip_ban_store_for_tests(store_path)
    store.add_ban("203.0.113.10", reason="test", source="manual")
    assert store_path.exists()
    mtime_before = store_path.stat().st_mtime
    time.sleep(0.05)
    removed = store.prune_expired()
    assert removed == 0
    mtime_after = store_path.stat().st_mtime
    assert mtime_after == mtime_before


def test_prune_expired_rewrites_when_expired_removed(tmp_path: Path) -> None:
    store_path = tmp_path / "web_ip_bans.json"
    store = reset_ip_ban_store_for_tests(store_path)
    store.add_ban("203.0.113.11", reason="temp", source="manual", duration_sec=0.01)
    time.sleep(0.05)
    mtime_before = store_path.stat().st_mtime
    time.sleep(0.05)
    removed = store.prune_expired()
    assert removed == 1
    assert store_path.stat().st_mtime >= mtime_before
    assert store.list_bans() == []
