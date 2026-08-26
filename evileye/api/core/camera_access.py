"""Per-user camera ACL and visible-camera prefs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from fastapi import HTTPException, Request

from evileye.api.core.user_prefs import (
    allowed_cameras_from_record,
    normalize_allowed_cameras,
    prefs_from_record,
)
from evileye.api.security import normalize_role


@dataclass(frozen=True)
class CameraAccess:
    unrestricted: bool
    allowed_names: frozenset[str]
    visible_names: frozenset[str] | None  # None = all allowed / unrestricted list

    @property
    def camera_access_label(self) -> str:
        return "all" if self.unrestricted else "restricted"


def lookup_user_record(username: str) -> Optional[dict[str, Any]]:
    """Dual-store lookup matching change-password / must-change order."""
    from evileye.api.core.credentials_users import get_credentials_user, list_credentials_users
    from evileye.api.core.user_store import get_user_store

    cred = get_credentials_user(username)
    if cred is None:
        for item in list_credentials_users():
            if str(item.get("username") or "").lower() == username.lower():
                return item
    if cred is not None:
        return cred
    return get_user_store().get_user_record(username)


def resolve_camera_access(request: Request) -> CameraAccess:
    auth = getattr(request.app.state, "web_auth", None)
    if auth is None or not getattr(auth, "enabled", False):
        return CameraAccess(unrestricted=True, allowed_names=frozenset(), visible_names=None)

    user = request.session.get("user")
    if not isinstance(user, dict):
        return CameraAccess(unrestricted=False, allowed_names=frozenset(), visible_names=frozenset())

    role = normalize_role(str(user.get("role") or "user"))
    username = str(user.get("username") or "")
    record = lookup_user_record(username) if username else None
    prefs = prefs_from_record(record)
    visible_raw = prefs.get("visible_cameras")
    visible_names: frozenset[str] | None
    if visible_raw is None:
        visible_names = None
    else:
        visible_names = frozenset(normalize_allowed_cameras(visible_raw))

    if role == "admin":
        return CameraAccess(unrestricted=True, allowed_names=frozenset(), visible_names=visible_names)

    allowed = frozenset(allowed_cameras_from_record(record))
    return CameraAccess(unrestricted=False, allowed_names=allowed, visible_names=visible_names)


def list_effective_names(access: CameraAccess) -> frozenset[str] | None:
    """
    Names for list endpoints.
    None = unrestricted (do not filter by name set).
    Empty frozenset = show nothing.
    """
    if access.unrestricted:
        if access.visible_names is None:
            return None
        return access.visible_names
    base = access.allowed_names
    if access.visible_names is None:
        return base
    return base & access.visible_names


def name_allowed_hard(access: CameraAccess, name: str) -> bool:
    """Hard ACL check (stream/WS/media). Prefs do not apply. System always allowed."""
    if access.unrestricted:
        return True
    cleaned = str(name or "").strip()
    if cleaned == "System":
        return True
    return cleaned in access.allowed_names


def assert_name_allowed(access: CameraAccess, name: str) -> None:
    if not name_allowed_hard(access, name):
        raise HTTPException(status_code=403, detail="Camera access denied")


def catalog_source_names(*, scope: str = "active") -> list[str]:
    from evileye.api.core.server_state import list_camera_summaries

    seen: set[str] = set()
    items: list[str] = []
    for row in list_camera_summaries(scope=scope):
        name = str(row.get("source_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        items.append(name)
    items.sort(key=str.lower)
    return items


def catalog_camera_items(*, scope: str = "active") -> list[dict[str, Any]]:
    from evileye.api.core.server_state import list_camera_summaries

    by_name: dict[str, dict[str, Any]] = {}
    for row in list_camera_summaries(scope=scope):
        name = str(row.get("source_name") or "").strip()
        if not name or name in by_name:
            continue
        by_name[name] = {
            "source_name": name,
            "source_id": row.get("source_id"),
            "source_type": row.get("source_type"),
            "run_id": row.get("run_id"),
        }
    return [by_name[k] for k in sorted(by_name.keys(), key=str.lower)]


def source_id_to_name(run_id: int, source_id: int | None) -> str | None:
    if source_id is None:
        return None
    try:
        from evileye.api.core.server_state import get_run_summary

        summary = get_run_summary(run_id)
    except Exception:
        return None
    if not isinstance(summary, dict):
        return None
    for item in summary.get("sources") or []:
        if not isinstance(item, dict):
            continue
        try:
            sid = int(item.get("source_id"))
        except (TypeError, ValueError):
            continue
        if sid == int(source_id):
            name = str(item.get("source_name") or "").strip()
            return name or None
    return None


def assert_source_id_allowed(access: CameraAccess, run_id: int, source_id: int | None) -> None:
    if access.unrestricted:
        return
    if source_id is None:
        # Single-source runs may omit source_id; resolve sole source if possible.
        try:
            from evileye.api.core.server_state import get_run_summary

            sources = (get_run_summary(run_id) or {}).get("sources") or []
        except Exception:
            sources = []
        if len(sources) == 1:
            name = str((sources[0] or {}).get("source_name") or "").strip()
            assert_name_allowed(access, name)
            return
        raise HTTPException(status_code=403, detail="Camera access denied")
    name = source_id_to_name(run_id, source_id)
    if not name:
        raise HTTPException(status_code=403, detail="Camera access denied")
    assert_name_allowed(access, name)


def filter_by_source_name(
    items: Iterable[dict[str, Any]],
    access: CameraAccess,
    *,
    key: str = "source_name",
    use_visible: bool = True,
    allow_system: bool = False,
) -> list[dict[str, Any]]:
    names = list_effective_names(access) if use_visible else (
        None if access.unrestricted else access.allowed_names
    )
    if names is None:
        return list(items)
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or "").strip()
        if allow_system and value == "System":
            result.append(item)
            continue
        if value in names:
            result.append(item)
    return result


def filter_sources_list(
    sources: Any,
    access: CameraAccess,
    *,
    use_visible: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        return []
    return filter_by_source_name(
        [s for s in sources if isinstance(s, dict)],
        access,
        key="source_name",
        use_visible=use_visible,
    )


def intersect_camera_query(access: CameraAccess, names: list[str], *, hard: bool = True) -> list[str]:
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    if access.unrestricted and not hard:
        effective = list_effective_names(access)
        if effective is None:
            return cleaned
        return [n for n in cleaned if n in effective]
    if access.unrestricted:
        return cleaned
    allowed = access.allowed_names if hard else (list_effective_names(access) or frozenset())
    return [n for n in cleaned if n in allowed]


def allowed_source_ids_for_run(access: CameraAccess, run_id: int) -> set[int] | None:
    """None = unrestricted (all ids). Empty set = none."""
    if access.unrestricted:
        return None
    try:
        from evileye.api.core.server_state import get_run_summary

        sources = (get_run_summary(run_id) or {}).get("sources") or []
    except Exception:
        return set()
    ids: set[int] = set()
    for item in sources:
        if not isinstance(item, dict):
            continue
        name = str(item.get("source_name") or "").strip()
        if name not in access.allowed_names:
            continue
        try:
            ids.add(int(item.get("source_id")))
        except (TypeError, ValueError):
            continue
    return ids
