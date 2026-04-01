from fastapi import APIRouter, Query

from evileye.api.core.journal_service import load_config_history, load_events_page, load_objects_page, load_system_logs


router = APIRouter(prefix="/api/v1/journals", tags=["journals"])


@router.get("/events")
async def journal_events(
    page: int = Query(0, ge=0),
    size: int = Query(30, ge=1, le=200),
    source_name: str | None = None,
    event_type: str | None = None,
) -> dict:
    filters = {}
    if source_name:
        filters["source_name"] = source_name
    if event_type:
        filters["event_type"] = event_type
    return load_events_page(page=page, size=size, filters=filters)


@router.get("/objects")
async def journal_objects(
    page: int = Query(0, ge=0),
    size: int = Query(30, ge=1, le=200),
    source_name: str | None = None,
    event_type: str | None = None,
) -> dict:
    filters = {}
    if source_name:
        filters["source_name"] = source_name
    if event_type:
        filters["event_type"] = event_type
    return load_objects_page(page=page, size=size, filters=filters)


@router.get("/logs")
async def journal_logs(lines: int = Query(80, ge=10, le=500)) -> dict:
    return load_system_logs(lines=lines)


@router.get("/config-history")
async def journal_config_history(limit: int = Query(50, ge=1, le=200)) -> dict:
    return load_config_history(limit=limit)
