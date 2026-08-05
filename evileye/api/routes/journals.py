from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

import asyncio
import mimetypes
import os

from evileye.api.core.journal_service import (
    DateScopeError,
    JournalPathForbidden,
    JournalPathNotFound,
    compare_config_history,
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
    restore_config_history,
)

router = APIRouter(prefix="/api/v1/journals", tags=["journals"])

_THUMB_CACHE: dict[tuple[str, int, float], bytes] = {}
_THUMB_CACHE_MAX = 256
_EXPORT_HARD_CAP = 5000


def _filters(source_name: str | None, event_type: str | None) -> dict:
    filters = {}
    if source_name:
        filters["source_name"] = source_name
    if event_type:
        filters["event_type"] = event_type
    return filters


def _date_kwargs(
        date: str | None,
        date_from: str | None,
        date_to: str | None,
) -> dict:
    return {"date": date, "date_from": date_from, "date_to": date_to}


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


def _resize_jpeg(path: str, width: int) -> bytes | None:
    """Best-effort thumbnail; returns None to fall back to full file."""
    try:
        st = os.stat(path)
        key = (path, int(width), float(st.st_mtime))
        cached = _THUMB_CACHE.get(key)
        if cached is not None:
            return cached
    except OSError:
        return None

    data: bytes | None = None
    try:
        import cv2  # type: ignore

        img = cv2.imread(path)
        if img is None:
            return None
        h, w = img.shape[:2]
        if w <= width:
            with open(path, "rb") as fh:
                data = fh.read()
        else:
            new_h = max(1, int(h * (width / float(w))))
            resized = cv2.resize(img, (width, new_h), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if not ok:
                return None
            data = buf.tobytes()
    except Exception:
        return None

    if data is None:
        return None
    if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX:
        _THUMB_CACHE.clear()
    _THUMB_CACHE[key] = data
    return data


@router.get("/events")
async def journal_events(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict:
    try:
        return await asyncio.to_thread(
            load_events_page,
            page=page,
            size=size,
            filters=_filters(source_name, event_type),
            **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events/grouped")
async def journal_events_grouped(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict:
    try:
        return await asyncio.to_thread(
            load_events_grouped_page,
            page=page,
            size=size,
            filters=_filters(source_name, event_type),
            **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/objects")
async def journal_objects(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict:
    try:
        return await asyncio.to_thread(
            load_objects_page,
            page=page,
            size=size,
            filters=_filters(source_name, event_type),
            **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/objects/grouped")
async def journal_objects_grouped(
        page: int = Query(0, ge=0),
        size: int = Query(30, ge=1, le=200),
        source_name: str | None = None,
        event_type: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict:
    try:
        return await asyncio.to_thread(
            load_objects_grouped_page,
            page=page,
            size=size,
            filters=_filters(source_name, event_type),
            **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/filters/meta")
async def journal_filters_meta() -> dict:
    return await asyncio.to_thread(load_filters_meta)


@router.get("/stats")
async def journal_stats(
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict:
    try:
        return await asyncio.to_thread(
            load_journal_stats, **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/row-meta")
async def journal_row_meta(
        row_key: str = Query(..., min_length=1),
        journal_type: str = Query("events", pattern="^(events|objects)$"),
        meta_only: bool = Query(True),
) -> dict:
    try:
        return await asyncio.to_thread(
            load_row_meta, row_key_value=row_key, journal_type=journal_type, meta_only=meta_only,
        )
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Row metadata not found")


@router.get("/preview")
async def journal_preview(
        path: str = Query(..., min_length=1),
        date: str | None = None,
        journal_type: str = Query("events", pattern="^(events|objects)$"),
        mode: str = Query("found", pattern="^(found|lost)$"),
        w: int | None = Query(None, ge=16, le=1280),
):
    try:
        secured = await asyncio.to_thread(
            resolve_secured_journal_file,
            resolver=lambda: resolve_journal_preview_path(
                path=path, date=date, journal_type=journal_type, mode=mode,
            ),
        )
    except JournalPathForbidden:
        raise HTTPException(status_code=403, detail="Path outside data directory")
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Preview image not found")
    if w:
        thumb = await asyncio.to_thread(_resize_jpeg, secured, int(w))
        if thumb is not None:
            from fastapi.responses import Response

            return Response(
                content=thumb,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"},
            )
    return _file_response(secured, media_type=_media_type_for_path(secured, "image/jpeg"))


@router.get("/frame")
async def journal_frame(
        path: str = Query(..., min_length=1),
        date: str | None = None,
        journal_type: str = Query("events", pattern="^(events|objects)$"),
        mode: str = Query("found", pattern="^(found|lost)$"),
):
    try:
        secured = await asyncio.to_thread(
            resolve_secured_journal_file,
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
        secured = await asyncio.to_thread(
            resolve_secured_journal_file,
            resolver=lambda: resolve_journal_video_path(path=path),
        )
    except JournalPathForbidden:
        raise HTTPException(status_code=403, detail="Path outside data directory")
    except JournalPathNotFound:
        raise HTTPException(status_code=404, detail="Video not found")
    return _file_response(secured, media_type=_media_type_for_path(secured, "video/mp4"))


@router.get("/config-history")
async def journal_config_history(limit: int = Query(50, ge=1, le=200)) -> dict:
    return await asyncio.to_thread(load_config_history, limit=limit)


@router.get("/config-history/compare")
async def journal_config_history_compare(
    a: int = Query(..., ge=1),
    b: int = Query(..., ge=1),
) -> dict:
    return await asyncio.to_thread(compare_config_history, a, b)


@router.post("/config-history/{job_id}/restore")
async def journal_config_history_restore(job_id: int, target_name: str = Query(...)) -> dict:
    try:
        return await asyncio.to_thread(restore_config_history, job_id, target_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _export_csv_chunks(items: list[dict]):
    import csv
    import io

    fields = ["time", "event", "information", "source", "time_lost", "row_key"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)
    for row in items:
        writer.writerow({k: row.get(k, "") for k in fields})
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


@router.get("/export")
async def journal_export(
    type: str = Query("events"),
    format: str = Query("json"),
    source_name: str | None = None,
    event_type: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(0, ge=0),
    size: int = Query(200, ge=1, le=1000),
):
    from fastapi.responses import JSONResponse

    if type not in {"events", "objects"}:
        raise HTTPException(status_code=400, detail="type must be events|objects")
    if format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="format must be json|csv")
    filters = _filters(source_name, event_type)
    # Cap total export size; stream CSV when possible
    export_size = min(size, _EXPORT_HARD_CAP)
    loader = load_objects_grouped_page if type == "objects" else load_events_grouped_page
    try:
        data = await asyncio.to_thread(
            loader,
            page=page,
            size=export_size,
            filters=filters,
            **_date_kwargs(date, date_from, date_to),
        )
    except DateScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = data.get("items") or []
    truncated = bool(data.get("has_more")) or len(items) >= _EXPORT_HARD_CAP
    headers = {"X-Export-Truncated": "1" if truncated else "0"}
    if format == "json":
        return JSONResponse(items, headers=headers)
    return StreamingResponse(
        _export_csv_chunks(items),
        media_type="text/csv",
        headers={**headers, "Content-Disposition": f'attachment; filename="{type}.csv"'},
    )
