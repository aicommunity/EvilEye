"""Reaudit R07: semaphore acquire counts toward state route deadline."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from evileye.api.routes import state as state_routes


def test_state_queue_deadline_returns_cached_or_503():
    async def _main():
        sem = asyncio.Semaphore(0)  # never available
        cached = {"ok": True}
        result = await state_routes._to_thread_with_timeout_or_cached(
            lambda: {"fresh": True},
            lambda: cached,
            timeout_sec=0.05,
            err_detail="state timeout",
            slot_sem=sem,
        )
        assert result == cached
        with pytest.raises(HTTPException) as exc:
            await state_routes._to_thread_with_timeout_or_cached(
                lambda: {"fresh": True},
                lambda: None,
                timeout_sec=0.05,
                err_detail="state timeout",
                slot_sem=sem,
            )
        assert exc.value.status_code == 503

    asyncio.run(_main())
