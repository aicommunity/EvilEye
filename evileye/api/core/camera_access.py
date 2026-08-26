"""Per-user camera ACL and visible-camera prefs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    return [item["source_name"] for item in catalog_camera_items(scope=scope)]


def _add_catalog_name(
    by_name: dict[str, dict[str, Any]],
    name: str,
    *,
    source_id: Any = None,
    source_type: Any = None,
    run_id: Any = None,
    config: str | None = None,
) -> None:
    cleaned = str(name or "").strip()
    if not cleaned or cleaned == "System":
        return
    prev = by_name.get(cleaned) or {}
    by_name[cleaned] = {
        "source_name": cleaned,
        "source_id": source_id if source_id is not None else prev.get("source_id"),
        "source_type": source_type or prev.get("source_type"),
        "run_id": run_id if run_id is not None else prev.get("run_id"),
        "config": config or prev.get("config"),
    }


def _names_from_config_path(path: Path, by_name: dict[str, dict[str, Any]]) -> None:
    from evileye.api.core.server_state import load_config_summary

    try:
        summary = load_config_summary(str(path))
    except Exception:
        summary = None
    if summary is not None:
        for item in summary.source_items or []:
            _add_catalog_name(
                by_name,
                str(item.get("source_name") or ""),
                source_id=item.get("source_id"),
                source_type=item.get("source_type"),
                config=path.name,
            )

    # Raw fallback: pick up names even when load_config_summary shape is incomplete.
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    pipeline = payload.get("pipeline") if isinstance(payload.get("pipeline"), dict) else payload
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    if not isinstance(sources, list):
        return
    for src in sources:
        if not isinstance(src, dict):
            continue
        names = src.get("source_names")
        if isinstance(names, list) and names:
            for n in names:
                _add_catalog_name(by_name, str(n), source_type=src.get("source") or src.get("type"), config=path.name)
            continue
        single = src.get("source_name") or src.get("name")
        if single:
            _add_catalog_name(by_name, str(single), source_type=src.get("source") or src.get("type"), config=path.name)


def _names_from_config_files() -> list[dict[str, Any]]:
    """Catalog from configs/*.json under site_root."""
    from pathlib import Path

    from evileye.core.paths import configs_dir

    by_name: dict[str, dict[str, Any]] = {}
    cfg_dir = configs_dir()
    if not cfg_dir.exists():
        return []
    for path in sorted(cfg_dir.glob("*.json")):
        try:
            _names_from_config_path(Path(path), by_name)
        except Exception:
            continue
    return [by_name[k] for k in sorted(by_name.keys(), key=str.lower)]


def _names_from_setup_default(by_name: dict[str, dict[str, Any]]) -> None:
    """Ensure system.json / setup default_config and basic projection names are included."""
    from pathlib import Path

    from evileye.core.paths import configs_dir, creds_path

    cfg_dir = configs_dir()
    default_name = "system.json"
    try:
        import json

        creds = json.loads(creds_path().read_text(encoding="utf-8"))
        setup = creds.get("setup") if isinstance(creds, dict) else None
        if isinstance(setup, dict) and setup.get("default_config"):
            default_name = str(setup.get("default_config"))
    except Exception:
        pass

    for name in {default_name, "system.json"}:
        path = cfg_dir / name
        if path.is_file():
            _names_from_config_path(path, by_name)

    # Basic projection (name + extra_names) from default config
    try:
        from evileye.api.core.setup_basic_merge import project_basic_from_config

        path = cfg_dir / default_name
        if not path.is_file():
            path = cfg_dir / "system.json"
        if not path.is_file():
            return
        import json

        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            return
        creds: dict[str, Any] = {}
        try:
            raw = json.loads(creds_path().read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                creds = raw
        except Exception:
            pass
        basic = project_basic_from_config(config, creds, config_name=path.name)
        for src in basic.get("sources") or []:
            if not isinstance(src, dict):
                continue
            _add_catalog_name(by_name, str(src.get("name") or ""), config=path.name)
            for extra in src.get("extra_names") or []:
                _add_catalog_name(by_name, str(extra), config=path.name)
    except Exception:
        return


def _names_from_summaries(by_name: dict[str, dict[str, Any]], *, scopes: tuple[str, ...]) -> None:
    from evileye.api.core.server_state import list_camera_summaries

    for scope in scopes:
        try:
            rows = list_camera_summaries(scope=scope)
        except Exception:
            continue
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            _add_catalog_name(
                by_name,
                str(row.get("source_name") or ""),
                source_id=row.get("source_id"),
                source_type=row.get("source_type"),
                run_id=row.get("run_id"),
            )


def catalog_camera_items(*, scope: str = "active") -> list[dict[str, Any]]:
    """Unique source_names for ACL UI from configs, setup, live state, and stored ACLs."""
    by_name: dict[str, dict[str, Any]] = {}
    for item in _names_from_config_files():
        by_name[item["source_name"]] = item
    _names_from_setup_default(by_name)

    scopes = (scope, "all") if scope != "all" else ("all",)
    # Prefer requested scope first, then all; duplicates merge via _add_catalog_name.
    unique_scopes = tuple(dict.fromkeys(scopes + ("active", "current", "all")))
    _names_from_summaries(by_name, scopes=unique_scopes)

    try:
        from evileye.api.core.credentials_users import list_credentials_users
        from evileye.api.core.user_prefs import allowed_cameras_from_record
        from evileye.api.core.user_store import get_user_store

        for record in list(list_credentials_users()) + list(get_user_store().list_users()):
            for name in allowed_cameras_from_record(record):
                _add_catalog_name(by_name, name)
    except Exception:
        pass

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
