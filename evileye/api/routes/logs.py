from fastapi import APIRouter, HTTPException, Query

from evileye.api.core.log_service import list_log_files, read_log_file

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("")
async def runtime_logs(limit: int = Query(50, ge=1, le=200)) -> dict:
    return list_log_files(limit=limit)


@router.get("/{filename}")
async def runtime_log_content(
        filename: str,
        tail: int | None = Query(None, ge=10, le=5000),
) -> dict:
    try:
        return read_log_file(filename, tail=tail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Log file not found") from None
