from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from evileye.api.core.journal_service import (
    load_config_history,
    load_events_grouped_page,
    load_events_page,
    load_objects_grouped_page,
    load_objects_page,
    resolve_journal_preview_path,
)

router = APIRouter(prefix="/api/v1/journals", tags=["journals"])


def _filters(source_name: str | None, event_type: str | None) -> dict:
    filters = {}
    if source_name:
        filters["source_name"] = source_name
    if event_type:
        filters["event_type"] = event_type
    return filters


@router.get("/events")
async def journal_events(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
) -> dict:
    return load_events_page(page=page, size=size, filters=_filters(source_name, event_type), date=date)


@router.get("/events/grouped")
async def journal_events_grouped(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
) -> dict:
    return load_events_grouped_page(page=page, size=size, filters=_filters(source_name, event_type), date=date)


@router.get("/objects")
async def journal_objects(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
) -> dict:
    return load_objects_page(page=page, size=size, filters=_filters(source_name, event_type), date=date)


@router.get("/objects/grouped")
async def journal_objects_grouped(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
) -> dict:
    return load_objects_grouped_page(page=page, size=size, filters=_filters(source_name, event_type), date=date)


@router.get("/preview")
async def journal_preview(
        path: str = Query(..., min_length=1),
        date: str | None = None,
        journal_type: str = Query("events", pattern="^(events|objects)$"),
):
    resolved = resolve_journal_preview_path(path=path, date=date, journal_type=journal_type)
    if not resolved:
        raise HTTPException(status_code=404, detail="Preview image not found")
    return FileResponse(resolved)


@router.get("/config-history")
async def journal_config_history(limit: int = Query(50, ge=1, le=200)) -> dict:
    return load_config_history(limit=limit)
