from fastapi import APIRouter, HTTPException, Query

from evileye.api.core.server_state import (
    build_overview,
    build_runtime_history,
    get_current_run_summary,
    get_run_summary,
    list_camera_summaries,
    list_history_run_summaries,
    list_run_summaries,
)


router = APIRouter(prefix="/api/v1/state", tags=["state"])


@router.get("/overview")
async def state_overview() -> dict:
    return build_overview()


@router.get("/runs")
async def state_runs(scope: str = Query("current", pattern="^(current|history|all)$")) -> dict:
    if scope == "current":
        current = get_current_run_summary()
        return {"current_run": current, "items": [current] if current else []}
    if scope == "history":
        return {"current_run": get_current_run_summary(), "items": list_history_run_summaries(exclude_current=True)}
    return {"current_run": get_current_run_summary(), "items": list_run_summaries()}


@router.get("/history")
async def state_history() -> dict:
    return build_runtime_history()


@router.get("/runs/{rid}")
async def state_run(rid: int) -> dict:
    item = get_run_summary(rid)
    if item is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return item


@router.get("/cameras")
async def state_cameras(scope: str = Query("current", pattern="^(current|all)$")) -> dict:
    return {"items": list_camera_summaries(current_only=(scope != "all"))}
