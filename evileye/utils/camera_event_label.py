"""Helpers for camera identity in events/journals (no credentials in stored/displayed text)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# scheme://user:pass@host → scheme://host (drop userinfo entirely)
_MEDIA_USERINFO_RE = re.compile(r"(rtsp[s]?://|https?://)([^/@\s]+)@", re.IGNORECASE)


def looks_like_media_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return "://" in text or text.startswith("rtsp")


def redact_media_url_credentials(text: str) -> str:
    """Remove credentials embedded in media URLs inside ``text``."""
    if not text:
        return text
    return _MEDIA_USERINFO_RE.sub(r"\1", text)


def media_url_without_credentials(url: str) -> str:
    """Return URL without userinfo (credentials). Prefer host+path for RTSP."""
    if not url:
        return ""
    raw = str(url).strip()
    try:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.hostname:
            netloc = parsed.hostname
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            path = parsed.path or ""
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{parsed.scheme}://{netloc}{path}{query}"
    except Exception:
        pass
    return redact_media_url_credentials(raw)


def source_names_label(source_names: Optional[Union[Sequence[Any], Any]]) -> str:
    """Join source_names into a stable display label."""
    if source_names is None:
        return ""
    if isinstance(source_names, (str, bytes)):
        text = str(source_names).strip()
        return text
    names: list[str] = []
    for item in source_names:
        text = str(item).strip()
        if text:
            names.append(text)
    return ", ".join(names)


def camera_event_identity(
    *,
    source_names: Optional[Union[Sequence[Any], Any]] = None,
    address: Optional[str] = None,
) -> str:
    """Preferred identity for CameraEvent: stream name(s), else URL without credentials."""
    names = source_names_label(source_names)
    if names and not looks_like_media_url(names):
        return names
    if address:
        return media_url_without_credentials(address)
    if names:
        return media_url_without_credentials(names)
    return ""


def format_camera_event_information(identity: str, *, connected: bool) -> str:
    status = "reconnect" if connected else "disconnect"
    label = identity or "camera"
    if looks_like_media_url(label):
        label = media_url_without_credentials(label)
    else:
        label = redact_media_url_credentials(label)
    return f"Camera={label} {status}"


def resolve_source_name_from_mappings(
    address: str,
    mappings: Optional[Mapping[str, Tuple[Any, str]]] = None,
) -> str:
    """Match camera address (with/without credentials) to configured stream name."""
    if not address or not mappings:
        return ""
    needle = media_url_without_credentials(address)
    for source_name, (_source_id, mapped_address) in mappings.items():
        if not mapped_address:
            continue
        if mapped_address == address or media_url_without_credentials(str(mapped_address)) == needle:
            return str(source_name)
    return ""


def sanitize_camera_event_record(
    rec: dict[str, Any],
    *,
    source_mappings: Optional[Mapping[str, Tuple[Any, str]]] = None,
) -> dict[str, Any]:
    """Sanitize a persisted/loaded camera event dict for API/UI (copy)."""
    out = dict(rec)
    address = str(out.get("camera_full_address") or "")
    resolved = resolve_source_name_from_mappings(address, source_mappings)
    identity = camera_event_identity(
        source_names=out.get("source_names") or resolved or out.get("source_name"),
        address=address,
    )
    if identity:
        out["camera_full_address"] = identity
        if not out.get("source_name") or looks_like_media_url(str(out.get("source_name") or "")):
            out["source_name"] = identity

    connected = out.get("connection_status", False)
    if isinstance(connected, str):
        lowered = connected.lower()
        connected = "reconnect" in lowered or lowered in ("true", "1", "connected", "yes")
    else:
        connected = bool(connected)
    out["connection_status"] = connected
    if identity or out.get("information"):
        out["information"] = format_camera_event_information(identity, connected=connected)

    for key in ("camera_full_address", "source_name", "information", "source"):
        if key in out and isinstance(out[key], str):
            value = out[key]
            out[key] = (
                media_url_without_credentials(value)
                if looks_like_media_url(value)
                else redact_media_url_credentials(value)
            )
    return out
