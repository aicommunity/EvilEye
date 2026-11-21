#!/usr/bin/env python3
"""API probes: playback cameras/segments/detections as admin / full-user / playback-test."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from evileye.api.app import AuthGuardMiddleware
from evileye.api.core.camera_access import CameraAccess
from evileye.api.middleware.adaptive_session import AdaptiveSessionMiddleware
from evileye.api.routes.playback import router as playback_router
from evileye.api.security import permissions_for_role

DAYS = ["2026-09-05", "2026-09-07", "2026-09-08", "2026-09-09"]
RUN_ID = 1


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthGuardMiddleware)
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=False,
    )
    app.state.web_auth = SimpleNamespace(enabled=True, internal_token="")

    @app.post("/login")
    async def login(request: Request):
        body = await request.json()
        role = body.get("role", "user")
        username = body.get("username", "user")
        allowed = body.get("allowed")
        request.session["user"] = {
            "username": username,
            "role": role,
            "permissions": permissions_for_role(role),
            "allowed_cameras": allowed,
        }
        return {"ok": True}

    app.include_router(playback_router)
    return app


def _patch_access(monkey_targets: list, access: CameraAccess):
    import evileye.api.routes.playback as pb

    monkey_targets.append(
        (
            pb,
            "resolve_camera_access",
            getattr(pb, "resolve_camera_access"),
        )
    )
    pb.resolve_camera_access = lambda request: access  # type: ignore[assignment]


def probe(identity: str, role: str, allowed: list[str] | None) -> list[dict[str, Any]]:
    import evileye.api.routes.playback as pb

    orig = pb.resolve_camera_access
    if role == "admin":
        access = CameraAccess(unrestricted=True, allowed_names=frozenset(), visible_names=None)
    else:
        access = CameraAccess(
            unrestricted=False,
            allowed_names=frozenset(allowed or []),
            visible_names=None,
        )
    pb.resolve_camera_access = lambda request: access  # type: ignore[assignment]
    try:
        client = TestClient(_app())
        client.post(
            "/login",
            json={"username": identity, "role": role, "allowed": allowed},
        )
        rows = []
        for day in DAYS:
            t0 = time.time()
            cam = client.get(f"/api/v1/playback/cameras", params={"date": day, "run_id": RUN_ID})
            ms = int((time.time() - t0) * 1000)
            items = (cam.json() or {}).get("items") if cam.status_code == 200 else []
            ids = [i.get("id") for i in items or []]
            avail = [i.get("id") for i in items or [] if i.get("available") or i.get("has_stream_segments")]
            flags = {
                "has_ticks": any(i.get("has_detection_ticks") for i in items or []),
                "has_events": any(i.get("has_events") for i in items or []),
                "shares": {
                    i.get("id"): i.get("shares_media_with")
                    for i in items or []
                    if i.get("shares_media_with")
                },
            }
            t1 = time.time()
            cams_q = ",".join(ids) if ids else "Cam1"
            det = client.get(
                "/api/v1/playback/detections",
                params={
                    "date": day,
                    "run_id": RUN_ID,
                    "ticks_only": "true",
                    "cameras": cams_q,
                },
            )
            det_ms = int((time.time() - t1) * 1000)
            rows.append(
                {
                    "user": identity,
                    "day": day,
                    "cameras_status": cam.status_code,
                    "cameras_ms": ms,
                    "ids": ids,
                    "available_ids": avail,
                    "flags": flags,
                    "detections_status": det.status_code,
                    "detections_ms": det_ms,
                }
            )
        return rows
    finally:
        pb.resolve_camera_access = orig


def main() -> None:
    identities = [
        ("admin", "admin", None),
        ("full-user", "user", ["Cam1", "Cam2", "Cam3", "Cam4", "Cam5"]),
        ("playback-test", "user", ["Cam1", "Cam2"]),
    ]
    all_rows = []
    for name, role, allowed in identities:
        print(f"=== {name} ===")
        rows = probe(name, role, allowed)
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
            all_rows.append(r)
    from pathlib import Path

    out_path = Path("/home/user/EvilEyeDeploy/logs/archive_api_probe.json")
    out_path.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
