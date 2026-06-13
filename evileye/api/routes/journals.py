from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

import mimetypes

from evileye.api.core.journal_service import (
    JournalPathForbidden,
    JournalPathNotFound,
    load_config_history,
    load_events_grouped_page,
    load_events_page,
    load_filters_meta,
    load_journal_stats,
    load_objects_grouped_page,
    load_objects_page,
    load_row_meta,
    resolve_journal_frame_path,
    resolve_journal_preview_path,
    resolve_journal_video_path,
    resolve_secured_journal_file,
)

router = APIRouter(prefix="/api/v1/journals", tags=["journals"])


def _filters(source_name: str | None, event_type: str | None) -> dict:
    filters = {}
    if source_name:
        filters["source_name"] = source_name
    if event_type:
        filters["event_type"] = event_type
    return filters


def _media_type_for_path(path: str, fallback: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or fallback


def _file_response(path: str, *, media_type: str | None = None) -> FileResponse:
    mt = media_type or _media_type_for_path(path, "application/octet-stream")
    return FileResponse(
        path,
        media_type=mt,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )


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


@router.get("/filters/meta")
async def journal_filters_meta() -> dict:
    return load_filters_meta()


@router.get("/stats")
async def journal_stats(date: str | None = None) -> dict:
    return load_journal_stats(date=date)


@router.get("/row-meta")
async def journal_row_meta(
        row_key: str = Query(..., min_length=1),
        journal_type: str = Query("events", pattern="^(events|objects)$"),
) -> dict:
    try:
        return load_row_meta(row_key_value=row_key, journal_type=journal_type)
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Row metadata not found")


@router.get("/preview")
async def journal_preview(
        path: str = Query(..., min_length=1),
        date: str | None = None,
        journal_type: str = Query("events", pattern="^(events|objects)$"),
        mode: str = Query("found", pattern="^(found|lost)$"),
):
    try:
        secured = resolve_secured_journal_file(
            resolver=lambda: resolve_journal_preview_path(
                path=path, date=date, journal_type=journal_type, mode=mode,
            ),
        )
    except JournalPathForbidden:
        raise HTTPException(status_code=403, detail="Path outside data directory")
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Preview image not found")
    return _file_response(secured, media_type=_media_type_for_path(secured, "image/jpeg"))


@router.get("/frame")
async def journal_frame(
        path: str = Query(..., min_length=1),
        date: str | None = None,
        journal_type: str = Query("events", pattern="^(events|objects)$"),
        mode: str = Query("found", pattern="^(found|lost)$"),
):
    try:
        secured = resolve_secured_journal_file(
            resolver=lambda: resolve_journal_frame_path(
                path=path, date=date, journal_type=journal_type, mode=mode,
            ),
        )
    except JournalPathForbidden:
        raise HTTPException(status_code=403, detail="Path outside data directory")
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Frame image not found")
    return _file_response(secured, media_type=_media_type_for_path(secured, "image/jpeg"))


@router.get("/video")
async def journal_video(path: str = Query(..., min_length=1)):
    try:
        secured = resolve_secured_journal_file(
            resolver=lambda: resolve_journal_video_path(path=path),
        )
    except JournalPathForbidden:
        raise HTTPException(status_code=403, detail="Path outside data directory")
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Video not found")
    return _file_response(secured, media_type=_media_type_for_path(secured, "video/mp4"))


@router.get("/config-history")
async def journal_config_history(limit: int = Query(50, ge=1, le=200)) -> dict:
    return load_config_history(limit=limit)
