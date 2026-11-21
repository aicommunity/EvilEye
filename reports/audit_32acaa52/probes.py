"""Isolated audit reproductions for 32acaa52 (these assert observed defects).

Run from repository root: python reports/audit_32acaa52/probes.py --out result.json
Uses synthetic files/users only. Does not contact cameras or a running service.
Requires the project's API/test dependencies. Not a regression acceptance suite.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def media_probes(root):
    from fastapi.testclient import TestClient
    from evileye.api.app import create_app
    from evileye.api.security import hash_password
    from evileye.api.core import journal_service

    data = root / "EvilEyeData"
    files = {
        "Streams/2026-01-01/Cam2/seg.mp4": b"allowed-camera",
        "Streams/2026-01-01/Cam9/seg.mp4": b"forbidden-camera",
        "Events/2026-01-01/Videos/Cam9/clip.mp4": b"forbidden-event",
        "Events/2026-01-01/Metadata/private.json": b'{"camera":"Cam9"}',
    }
    for name, content in files.items():
        target = data / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    users = [
        {"username": "admin", "role": "admin", "password_hash": hash_password("audit-admin-local-only"), "disabled": False},
        {"username": "ops", "role": "user", "password_hash": hash_password("audit-ops-local-only"), "disabled": False, "allowed_cameras": ["Cam2"]},
    ]
    creds = {"web_auth": {"enabled": True, "session_secret": "audit-synthetic-session-secret-0123456789", "internal_token": "audit-local-only", "secure_cookies": False, "users": users}}
    (root / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    (root / "web_users.json").write_text('{"users":[]}', encoding="utf-8")
    previous = Path.cwd()
    os.chdir(root)
    try:
        # Only journal data-root discovery is replaced. Authentication, ACL,
        # routes, canonicalization and FileResponse are the actual application.
        with patch.dict(os.environ, {"EVILEYE_DATA_DIR": str(data)}), patch.object(journal_service, "_image_base_dir", return_value=str(data)):
            with TestClient(create_app()) as client:
                assert client.post("/api/v1/auth/login", json={"username": "ops", "password": "audit-ops-local-only"}).status_code == 200
                paths = {
                    "direct_denied": ("/api/v1/playback/media", "Streams/2026-01-01/Cam9/seg.mp4"),
                    "traversal_camera": ("/api/v1/playback/media", "Streams/2026-01-01/Cam2/../Cam9/seg.mp4"),
                    "traversal_metadata": ("/api/v1/playback/media", "Streams/2026-01-01/Cam2/../../../Events/2026-01-01/Metadata/private.json"),
                    "journal_camera": ("/api/v1/journals/video", "Events/2026-01-01/Videos/Cam9/clip.mp4"),
                    "journal_metadata": ("/api/v1/journals/video", "Events/2026-01-01/Metadata/private.json"),
                }
                result = {}
                for name, (url, path) in paths.items():
                    response = client.get(url, params={"path": path})
                    result[name] = {"status": response.status_code, "body": response.text}
                assert result["direct_denied"]["status"] == 403
                for name in paths.keys() - {"direct_denied"}:
                    assert result[name]["status"] == 200, result
                return result
    finally:
        os.chdir(previous)


def frozen_ticks(root):
    from evileye.api.core import playback_metadata_service as meta
    from evileye.api.core import playback_timeline_index as idx
    date = "2020-01-01"
    meta_dir = root / "Detections" / date / "Metadata"
    meta_dir.mkdir(parents=True)
    source = meta_dir / "objects_found.json"
    source.write_text("[]", encoding="utf-8")
    (meta_dir / "objects_lost.json").write_text("[]", encoding="utf-8")
    rows = [{"ts": 1.0, "kind": "found", "object_id": 1}]
    with patch.object(meta, "_load_params_for_run", return_value={}), patch.object(meta, "_playback_data_dir", return_value=root), patch.object(meta, "_load_day_index_by_camera", side_effect=lambda **kw: {"Cam1": list(rows)}) as loader:
        first = idx._rebuild_detection_ticks(date_folder=date, cameras=["Cam1"])
        rows.append({"ts": 2.0, "kind": "found", "object_id": 2})
        st = source.stat()
        os.utime(source, (st.st_atime, st.st_mtime + 10))
        second = idx._rebuild_detection_ticks(date_folder=date, cameras=["Cam1"])
        disk = json.loads((meta_dir / "detection_ticks.json").read_text())
        current_sig = meta._file_mtime_sum(source, meta_dir / "objects_lost.json")
        result = {"first_ticks": len(first["Cam1"]), "source_ticks_after_append": len(rows), "second_ticks": len(second["Cam1"]), "source_loader_calls": loader.call_count, "stale_data_marked_current": disk["source_mtime"] == current_sig}
        assert result["second_ticks"] == 1 and loader.call_count == 1 and result["stale_data_marked_current"]
        return result


def event_index_probes(root):
    from evileye.api.core import playback_service as svc
    from evileye.api.core import playback_timeline_index as idx
    date = "2020-02-01"
    (root / "Events" / date / "Metadata").mkdir(parents=True)
    raw = [{"camera": "Cam1", "ts": float(i), "event_type": "alarm", "label": str(i)} for i in range(2001)]
    with patch.object(svc, "data_dir", return_value=root), patch.object(svc, "_iter_event_rows", return_value=raw):
        capped = idx._rebuild_event_intervals(date_folder=date, cameras=["Cam1"], limit=10000)
    with patch.object(svc, "data_dir", return_value=root), patch.object(svc, "load_event_intervals", return_value=[]) as loader:
        idx.ensure_event_intervals(date_folder=date, cameras=["EmptyCam"])
        idx.ensure_event_intervals(date_folder=date, cameras=["EmptyCam"])
        result = {"input_rows": len(raw), "indexed_rows": len(capped), "empty_camera_rebuilds_for_two_requests": loader.call_count}
        assert len(capped) == 2000 and loader.call_count == 2
        return result


def concurrent_events(root):
    from evileye.api.core import playback_service as svc
    from evileye.api.core import playback_timeline_index as idx
    date = "2020-03-01"
    (root / "Events" / date / "Metadata").mkdir(parents=True)
    started, release = threading.Event(), threading.Event()
    follower_thread = []
    def loader(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return [{"camera": "Cam1", "start_ts": 1.0, "end_ts": 2.0}, {"camera": "Cam2", "start_ts": 1.0, "end_ts": 2.0}]
    def follower():
        follower_thread.append(threading.get_ident())
        return idx.ensure_event_intervals(date_folder=date, cameras=["Cam2"])
    with patch.object(svc, "data_dir", return_value=root), patch.object(svc, "load_event_intervals", side_effect=loader):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(idx.ensure_event_intervals, date_folder=date, cameras=["Cam1"])
            assert started.wait(5)
            b = pool.submit(follower)
            # Wait until the follower actually waits inside production SingleFlight.
            deadline = time.monotonic() + 3
            waiting = False
            while time.monotonic() < deadline:
                frame = sys._current_frames().get(follower_thread[0]) if follower_thread else None
                while frame:
                    if frame.f_code.co_filename.endswith("singleflight.py") and frame.f_code.co_name == "do" and frame.f_locals.get("leader") is False:
                        waiting = True
                    frame = frame.f_back
                if waiting:
                    break
                time.sleep(0.001)
            release.set()
            first, second = a.result(), b.result()
            assert waiting and second[0]["camera"] == "Cam1"
            return {"leader_requested": "Cam1", "follower_requested": "Cam2", "leader_received": [x["camera"] for x in first], "follower_received": [x["camera"] for x in second]}


def stale_cache():
    from evileye.api.core import playback_cache as cache
    cache.clear_memory_cache()
    cache.remember("audit-sticky", {"items": [1]})
    before = cache.recall("audit-sticky")
    fresh = cache.recall("audit-sticky", require_fresh=True)
    fallback = cache.recall("audit-sticky")
    cache.clear_memory_cache()
    assert before is not None and fresh is None and fallback is None
    return {"before": before, "fresh_lookup": fresh, "fallback_after_fresh_lookup": fallback}


async def queue_timeout():
    from evileye.api.routes import state
    start = time.perf_counter()
    outer_cancelled = False
    try:
        await asyncio.wait_for(state._to_thread_with_timeout_or_cached(lambda: "live", lambda: "stale", timeout_sec=0.01, err_detail="audit", slot_sem=asyncio.Semaphore(0)), timeout=0.1)
    except asyncio.TimeoutError:
        outer_cancelled = True
    assert outer_cancelled
    return {"configured_timeout_ms": 10, "outer_cancel_ms": round((time.perf_counter() - start) * 1000, 1), "helper_returned_stale_or_503": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="audit-", dir=args.scratch) as name:
        root = Path(name).resolve()
        result = {}
        for label, fn in [("media_acl", media_probes), ("frozen_detection_ticks", frozen_ticks), ("event_index", event_index_probes), ("singleflight_camera_isolation", concurrent_events)]:
            sub = root / label
            sub.mkdir()
            result[label] = fn(sub)
        result["stale_cache"] = stale_cache()
        result["state_queue_deadline"] = asyncio.run(queue_timeout())
    encoded = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
