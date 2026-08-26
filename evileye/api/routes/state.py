from fastapi import APIRouter, HTTPException, Query, Request
import asyncio
from copy import deepcopy

from evileye.api.core.camera_access import (
    filter_by_source_name,
    filter_sources_list,
    resolve_camera_access,
)
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


def _filter_run_summary(item: dict | None, access) -> dict | None:
    if not item or not isinstance(item, dict):
        return item
    out = dict(item)
    if "sources" in out:
        out["sources"] = filter_sources_list(out.get("sources"), access, use_visible=False)
    return out


def _filter_overview(payload: dict, access) -> dict:
    out = deepcopy(payload) if isinstance(payload, dict) else {}
    cameras = out.get("cameras")
    if isinstance(cameras, list):
        filtered = filter_by_source_name(cameras, access, key="source_name", use_visible=True)
        out["cameras"] = filtered
        out["cameras_total"] = len(filtered)
        out["web_previews_available"] = sum(1 for c in filtered if c.get("preview_available"))
    for key in ("current_run",):
        if key in out:
            out[key] = _filter_run_summary(out.get(key), access)
    active = out.get("active_runs")
    if isinstance(active, list):
        out["active_runs"] = [_filter_run_summary(r, access) for r in active if isinstance(r, dict)]
    return out


@router.get("/overview")
async def state_overview(request: Request) -> dict:
    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        payload = await _to_thread_with_timeout_or_cached(
            build_overview,
            get_cached_overview,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail="state_overview timeout",
        )
    return _filter_overview(payload, resolve_camera_access(request))


@router.get("/runs")
async def state_runs(
    request: Request,
    scope: str = Query("current", pattern="^(current|active|history|all)$"),
) -> dict:
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
        payload = await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail=f"state_runs({scope}) timeout",
        )
    access = resolve_camera_access(request)
    current = _filter_run_summary(payload.get("current_run"), access)
    items = payload.get("items") or []
    filtered_items = [_filter_run_summary(r, access) for r in items if isinstance(r, dict)]
    return {"current_run": current, "items": filtered_items}


@router.get("/history")
async def state_history(request: Request) -> dict:
    def _load() -> dict:
        return build_runtime_history()

    def _cached() -> dict | None:
        ok_c, current = probe_cached_current_run_summary()
        ok_a, active_items = probe_cached_active_run_summaries()
        if not ok_c and not ok_a:
            return None
        return {"current_run": current, "active_runs": active_items, "items": []}

    async with _STATE_HEAVY_ROUTE_SEMAPHORE:
        payload = await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            timeout_sec=_STATE_ROUTE_TIMEOUT_SEC,
            err_detail="state_history timeout",
        )
    access = resolve_camera_access(request)
    out = dict(payload) if isinstance(payload, dict) else {}
    out["current_run"] = _filter_run_summary(out.get("current_run"), access)
    if isinstance(out.get("active_runs"), list):
        out["active_runs"] = [_filter_run_summary(r, access) for r in out["active_runs"] if isinstance(r, dict)]
    if isinstance(out.get("items"), list):
        out["items"] = [_filter_run_summary(r, access) for r in out["items"] if isinstance(r, dict)]
    return out


@router.get("/runs/{rid}")
async def state_run(rid: int, request: Request) -> dict:
    try:
        item = await asyncio.wait_for(
            asyncio.to_thread(get_run_summary, rid),
            timeout=_STATE_ROUTE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="state_run timeout")
    if item is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _filter_run_summary(item, resolve_camera_access(request)) or item


@router.get("/cameras")
async def state_cameras(
    request: Request,
    scope: str = Query("active", pattern="^(current|active|all)$"),
) -> dict:
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
    access = resolve_camera_access(request)
    filtered = filter_by_source_name(items or [], access, key="source_name", use_visible=True)
    return {"items": filtered}
