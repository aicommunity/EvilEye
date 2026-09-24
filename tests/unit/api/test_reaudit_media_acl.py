"""Reaudit R01/R02: ACL after canonicalize — traversal and journal media must 403."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core import journal_service
from evileye.api.core.camera_access import CameraAccess
from evileye.api.core.media_access import (
    cameras_from_canonical,
    resolve_authorized_media,
    resolve_under_data_root,
)
from evileye.api.security import hash_password
from fastapi import HTTPException


ADMIN_PASSWORD = "correct-horse-battery"
USER_PASSWORD = "secretpassword"


def _write_creds(tmp_path, *, extra_users=None):
    users = [
        {
            "username": "admin",
            "password_hash": hash_password(ADMIN_PASSWORD),
            "role": "admin",
            "disabled": False,
        }
    ]
    if extra_users:
        users.extend(extra_users)
    creds = {
        "web_auth": {
            "enabled": True,
            "session_secret": "test-session-secret-not-default-0123456789",
            "internal_token": "test-internal-token",
            "secure_cookies": False,
            "users": users,
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    (tmp_path / "web_users.json").write_text(json.dumps({"users": []}), encoding="utf-8")


def test_cameras_from_canonical_after_traversal(tmp_path):
    data = tmp_path / "data"
    target = data / "Streams" / "2026-01-01" / "Cam9" / "seg.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    resolved = resolve_under_data_root(
        "Streams/2026-01-01/Cam2/../Cam9/seg.mp4", data
    )
    assert cameras_from_canonical(resolved, data) == ["Cam9"]


def test_resolve_authorized_denies_traversal_to_denied_cam(tmp_path):
    data = tmp_path / "data"
    target = data / "Streams" / "2026-01-01" / "Cam9" / "seg.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    access = CameraAccess(
        unrestricted=False,
        allowed_names=frozenset({"Cam2"}),
        visible_names=None,
    )
    with pytest.raises(HTTPException) as exc:
        resolve_authorized_media(
            access,
            "Streams/2026-01-01/Cam2/../Cam9/seg.mp4",
            data_root=data,
        )
    assert exc.value.status_code == 403


def test_resolve_authorized_denies_metadata_as_video(tmp_path):
    data = tmp_path / "data"
    meta = data / "Events" / "2026-01-01" / "Metadata" / "private.json"
    meta.parent.mkdir(parents=True)
    meta.write_text("{}", encoding="utf-8")
    access = CameraAccess(
        unrestricted=False,
        allowed_names=frozenset({"Cam2"}),
        visible_names=None,
    )
    with pytest.raises(HTTPException) as exc:
        resolve_authorized_media(
            access,
            "Events/2026-01-01/Metadata/private.json",
            data_root=data,
        )
    assert exc.value.status_code == 403


def test_reaudit_media_acl_http_matrix(tmp_path, monkeypatch):
    """Inverted probe: all attack paths 403; legitimate Cam2 still 200."""
    data = tmp_path / "EvilEyeData"
    files = {
        data / "Streams" / "2026-01-01" / "Cam9" / "seg.mp4": b"cam9",
        data / "Streams" / "2026-01-01" / "Cam2" / "seg.mp4": b"cam2",
        data / "Events" / "2026-01-01" / "Metadata" / "private.json": b'{"s":1}',
        data / "Events" / "2026-01-01" / "Videos" / "Cam9" / "clip.mp4": b"j9",
        data / "Events" / "2026-01-01" / "Videos" / "Cam2" / "clip.mp4": b"j2",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    _write_creds(
        tmp_path,
        extra_users=[
            {
                "username": "ops",
                "password_hash": hash_password(USER_PASSWORD),
                "role": "user",
                "disabled": False,
                "allowed_cameras": ["Cam2"],
            }
        ],
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(data))
    monkeypatch.chdir(tmp_path)

    with patch.object(journal_service, "_image_base_dir", return_value=str(data)):
        client = TestClient(create_app())
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "ops", "password": USER_PASSWORD},
            ).status_code
            == 200
        )

        assert (
            client.get(
                "/api/v1/playback/media",
                params={"path": "Streams/2026-01-01/Cam2/seg.mp4"},
            ).status_code
            == 200
        )

        denied = {
            "direct_denied": (
                "/api/v1/playback/media",
                "Streams/2026-01-01/Cam9/seg.mp4",
            ),
            "traversal_camera": (
                "/api/v1/playback/media",
                "Streams/2026-01-01/Cam2/../Cam9/seg.mp4",
            ),
            "traversal_metadata": (
                "/api/v1/playback/media",
                "Streams/2026-01-01/Cam2/../../../Events/2026-01-01/Metadata/private.json",
            ),
            "journal_camera": (
                "/api/v1/journals/video",
                "Events/2026-01-01/Videos/Cam9/clip.mp4",
            ),
            "journal_metadata": (
                "/api/v1/journals/video",
                "Events/2026-01-01/Metadata/private.json",
            ),
        }
        for name, (url, path) in denied.items():
            response = client.get(url, params={"path": path})
            assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"

        # Cache-Control must not be public for media.
        ok = client.get(
            "/api/v1/playback/media",
            params={"path": "Streams/2026-01-01/Cam2/seg.mp4"},
        )
        assert "no-store" in (ok.headers.get("cache-control") or "").lower()
