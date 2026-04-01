from fastapi import APIRouter, HTTPException

from evileye.api.core.server_state import build_overview, get_run_summary, list_camera_summaries, list_run_summaries


router = APIRouter(prefix="/api/v1/state", tags=["state"])


@router.get("/overview")
async def state_overview() -> dict:
    return build_overview()


@router.get("/runs")
async def state_runs() -> dict:
    return {"items": list_run_summaries()}


@router.get("/runs/{rid}")
async def state_run(rid: int) -> dict:
    item = get_run_summary(rid)
    if item is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return item


@router.get("/cameras")
async def state_cameras() -> dict:
    return {"items": list_camera_summaries()}
