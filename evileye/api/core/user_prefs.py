"""Shared normalization for user allowed_cameras and prefs fields."""

from __future__ import annotations

from typing import Any, Optional


def default_prefs() -> dict[str, Any]:
    return {
        "visible_cameras": None,
        "lang": None,
        "date_format": None,
    }


def normalize_allowed_cameras(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def normalize_prefs(raw: Any) -> dict[str, Any]:
    base = default_prefs()
    if not isinstance(raw, dict):
        return base
    if "visible_cameras" in raw:
        vis = raw.get("visible_cameras")
        if vis is None:
            base["visible_cameras"] = None
        elif isinstance(vis, list):
            base["visible_cameras"] = normalize_allowed_cameras(vis)
        else:
            base["visible_cameras"] = None
    lang = raw.get("lang")
    if lang in ("ru", "en"):
        base["lang"] = lang
    elif lang is None and "lang" in raw:
        base["lang"] = None
    date_format = raw.get("date_format")
    if date_format in ("DD-MM-YYYY", "YYYY-MM-DD", "MM-DD-YYYY"):
        base["date_format"] = date_format
    elif date_format is None and "date_format" in raw:
        base["date_format"] = None
    return base


def merge_prefs(existing: Any, patch: dict[str, Any]) -> dict[str, Any]:
    current = normalize_prefs(existing)
    if "visible_cameras" in patch:
        vis = patch.get("visible_cameras")
        if vis is None:
            current["visible_cameras"] = None
        elif isinstance(vis, list):
            current["visible_cameras"] = normalize_allowed_cameras(vis)
    if "lang" in patch:
        lang = patch.get("lang")
        if lang in ("ru", "en") or lang is None:
            current["lang"] = lang
    if "date_format" in patch:
        date_format = patch.get("date_format")
        if date_format in ("DD-MM-YYYY", "YYYY-MM-DD", "MM-DD-YYYY") or date_format is None:
            current["date_format"] = date_format
    return current


def allowed_cameras_from_record(record: Optional[dict[str, Any]]) -> list[str]:
    if not record:
        return []
    return normalize_allowed_cameras(record.get("allowed_cameras"))


def prefs_from_record(record: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not record:
        return default_prefs()
    return normalize_prefs(record.get("prefs"))
