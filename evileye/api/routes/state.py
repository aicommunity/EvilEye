from fastapi import APIRouter, HTTPException, Query
import asyncio

from evileye.api.core.server_state import (
    build_overview,
    build_runtime_history,
    list_active_run_summaries,
    get_current_run_summary,
    get_current_run_list_item,
    get_run_summary,
    list_camera_summaries,
    get_cached_overview,
    get_cached_camera_summaries,
    probe_cached_current_run_summary,
    probe_cached_active_run_summaries,
    list_history_run_list_items,
    list_run_list_items,
)

router = APIRouter(prefix="/api/v1/state", tags=["state"])

_STATE_ROUTE_TIMEOUT_SEC = 2.0
_STATE_HEAVY_ROUTE_SEMAPHORE = asyncio.Semaphore(3)


async def _to_thread_with_timeout_or_cached(value_fn, cached_fn, *, timeout_sec: float, err_detail: str):
    try:
        return await asyncio.wait_for(asyncio.to_thread(value_fn), timeout=timeout_sec)
    except asyncio.TimeoutError:
        cached = cached_fn()
        if cached is not None:
            return cached
        raise HTTPException(status_code=503, detail=err_detail)


@router.get("/overview")
async def state_overview() -> dict:
    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        return await _to_thread_with_timeout_or_cached(
            build_overview,
            get_cached_overview,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail="state_overview timeout",
        )


@router.get("/runs")
async def state_runs(scope: str = Query("current", pattern="^(current|active|history|all)$")) -> dict:
    def _load() -> dict:
        if scope == "current":
            current = get_current_run_summary()
            return {"current_run": current, "items": [current] if current else []}
        if scope == "active":
            return {"current_run": get_current_run_summary(), "items": list_active_run_summaries()}
        if scope == "history":
            return {
                "current_run": get_current_run_list_item(),
                "items": list_history_run_list_items(exclude_current=True),
            }
        return {"current_run": get_current_run_list_item(), "items": list_run_list_items()}

    def _cached() -> dict | None:
        if scope == "current":
            ok, current = probe_cached_current_run_summary()
            if not ok:
                return None
            return {"current_run": current, "items": [current] if current else []}

        if scope == "active":
            ok_c, current = probe_cached_current_run_summary()
            ok_a, active_items = probe_cached_active_run_summaries()
            if not ok_c and not ok_a:
                return None
            return {"current_run": current, "items": active_items}

        if scope == "history":
            return {
                "current_run": get_current_run_list_item(),
                "items": list_history_run_list_items(exclude_current=True),
            }

        return {
            "current_run": get_current_run_list_item(),
            "items": list_run_list_items(discover=False),
        }

    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        return await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail=f"state_runs({scope}) timeout",
        )


@router.get("/history")
async def state_history() -> dict:
    def _load() -> dict:
        return build_runtime_history()

    def _cached() -> dict | None:
        ok_c, current = probe_cached_current_run_summary()
        ok_a, active_items = probe_cached_active_run_summaries()
        if not ok_c and not ok_a:
            return None
        return {"current_run": current, "active_runs": active_items, "items": []}

    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        return await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail="state_history timeout",
        )


@router.get("/runs/{rid}")
async def state_run(rid: int) -> dict:
    item = await asyncio.to_thread(get_run_summary, rid)
    if item is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return item


@router.get("/cameras")
async def state_cameras(scope: str = Query("active", pattern="^(current|active|all)$")) -> dict:
    def _load():
        return list_camera_summaries(scope=scope)

    def _cached():
        return get_cached_camera_summaries(scope)

    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        items = await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail="state_cameras timeout",
        )
    return {"items": items}
