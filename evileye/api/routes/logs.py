from fastapi import APIRouter, Query

from evileye.api.core.log_service import load_runtime_logs

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("")
async def runtime_logs(
        lines: int = Query(80, ge=10, le=500),
        limit: int = Query(5, ge=1, le=20),
) -> dict:
    return load_runtime_logs(lines=lines, limit=limit)
