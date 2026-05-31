"""Multiprocessing spawn context for CUDA-safe workers."""

import multiprocessing as mp

import pytest

from evileye.core.mp_context import ensure_spawn_start_method, get_spawn_context


@pytest.mark.unit
def test_get_spawn_context_returns_spawn():
    ensure_spawn_start_method()
    ctx = get_spawn_context()
    assert ctx.get_start_method() == "spawn"
