"""Audit evidence for dcfc98dd. Assertions describe observed defects, not acceptance.

Run from repo root with API/test dependencies installed:
python reports/audit_dcfc98dd/backend_probes.py --scratch TEMP_DIR --out result.json
All users, media and state changes are confined to synthetic temporary storage.
"""
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
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def http_probes(root):
    from fastapi.testclient import TestClient
    from evileye.api.app import create_app
    from evileye.api.core import journal_service
    from evileye.api.security import hash_password

    data = root / 'EvilEyeData'
    paths = {
        'allowed_video': 'Streams/2026-01-01/Cam2/seg.mp4',
        'other_video': 'Streams/2026-01-01/Cam9/seg.mp4',
        'hyphen_camera': 'Streams/2026-01-01/Cam-2/seg.mp4',
        'object_preview': 'Detections/2026-01-01/Images/FoundPreviews/2026-01-01_12-00-00_Cam2_preview.jpeg',
        'event_preview': 'Events/2026-01-01/Images/FoundPreviews/2026-01-01_12-00-00_Cam2_preview.jpeg',
    }
    for name, rel in paths.items():
        f = data / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b'audit-synthetic-media')
    password = 'audit-local-synthetic-password'
    pw_hash = hash_password(password)
    users = [
        {'username': 'admin', 'role': 'admin', 'password_hash': pw_hash, 'disabled': False},
        {'username': 'secondadmin', 'role': 'admin', 'password_hash': pw_hash, 'disabled': False},
        {'username': 'ops', 'role': 'user', 'password_hash': pw_hash, 'disabled': False, 'allowed_cameras': ['Cam2', 'Cam-2']},
    ]
    creds = {'web_auth': {'enabled': True, 'session_secret': 'synthetic-audit-session-secret-0123456789', 'internal_token': 'synthetic-only', 'secure_cookies': False, 'users': users}}
    (root / 'credentials.json').write_text(json.dumps(creds), encoding='utf-8')
    (root / 'web_users.json').write_text('{"users":[]}', encoding='utf-8')
    previous = Path.cwd()
    os.chdir(root)
    try:
        with patch.dict(os.environ, {'EVILEYE_DATA_DIR': str(data)}), patch.object(journal_service, '_image_base_dir', return_value=str(data)):
            app = create_app()
            admin, second, ops = (TestClient(app) for _ in range(3))
            for client, name in [(admin, 'admin'), (second, 'secondadmin'), (ops, 'ops')]:
                assert client.post('/api/v1/auth/login', json={'username': name, 'password': password}).status_code == 200
            result = {}
            for client, label in [(admin, 'admin'), (ops, 'restricted')]:
                values = {}
                for name, rel in paths.items():
                    endpoint = '/api/v1/journals/preview' if 'preview' in name else '/api/v1/playback/media'
                    response = client.get(endpoint, params={'path': rel, 'journal_type': 'objects' if name == 'object_preview' else 'events'})
                    values[name] = response.status_code
                result[label] = values
            traversal = ops.get('/api/v1/playback/media', params={'path': 'Streams/2026-01-01/Cam2/../Cam9/seg.mp4'})
            result['old_traversal_now'] = traversal.status_code
            assert result['admin']['object_preview'] == 403
            assert result['restricted']['event_preview'] == 403
            assert result['restricted']['hyphen_camera'] == 403
            assert result['restricted']['allowed_video'] == 200 and traversal.status_code == 403

            assert admin.patch('/api/v1/users/ops', json={'disabled': True}).status_code == 200
            result['disabled_existing_session_media'] = ops.get('/api/v1/playback/media', params={'path': paths['allowed_video']}).status_code
            fresh = TestClient(app)
            result['disabled_fresh_login'] = fresh.post('/api/v1/auth/login', json={'username': 'ops', 'password': password}).status_code
            assert admin.patch('/api/v1/users/secondadmin', json={'role': 'user', 'allowed_cameras': ['Cam2']}).status_code == 200
            result['demoted_existing_session_users_api'] = second.get('/api/v1/users').status_code
            result['demoted_existing_session_other_camera'] = second.get('/api/v1/playback/media', params={'path': paths['other_video']}).status_code
            assert result['disabled_existing_session_media'] == 200
            assert result['disabled_fresh_login'] == 401
            assert result['demoted_existing_session_users_api'] == 200
            assert result['demoted_existing_session_other_camera'] == 200
            for client in (admin, second, ops, fresh):
                client.close()
            return result
    finally:
        os.chdir(previous)


async def unrestricted_ws_probe():
    from starlette.websockets import WebSocketDisconnect
    from evileye.api.routes import realtime
    from evileye.api.core.camera_access import CameraAccess
    from evileye.api.core.live_preview_hub import LivePreviewHub

    class Socket:
        scope = {'session': {'user': {'username': 'admin', 'role': 'admin'}}}
        accepted = False
        close_code = None
        received = 0
        async def accept(self): self.accepted = True
        async def close(self, code=1000): self.close_code = code
        async def receive_text(self):
            self.received += 1
            if self.received > 1: raise WebSocketDisconnect()
            return '{"op":"subscribe","source_ids":[0]}'
        async def send_json(self, data): pass
        async def send_bytes(self, data): pass

    ws = Socket()
    hub = LivePreviewHub()
    # Actual route and actual allowed_source_ids_for_run; external handshake/run discovery replaced.
    with patch.object(realtime, '_authorize_live_ws', new=AsyncMock(return_value=True)), patch.object(realtime, '_resolve_run', return_value={'id': 7, 'state': 'running'}), patch.object(realtime, '_camera_access_from_websocket', return_value=CameraAccess(True, frozenset(), None)), patch.object(realtime, '_touch_preview_demand_ws'), patch.object(realtime, 'get_live_preview_hub', return_value=hub):
        await realtime.live_grid_preview_ws(ws, 7)
    assert ws.accepted and ws.close_code == 4403
    return {'unrestricted': True, 'accepted': ws.accepted, 'close_on_first_subscribe': ws.close_code}


def index_probes(root):
    from evileye.api.core import playback_metadata_service as meta, playback_service as svc, playback_timeline_index as idx
    date = '2020-03-01'
    (root / 'Detections' / date / 'Metadata').mkdir(parents=True)
    entered, release = threading.Event(), threading.Event()
    tid = []
    def loader(**kw):
        entered.set()
        assert release.wait(5)
        return {cam: [{'ts': 1.0, 'kind': 'found', 'object_id': 1}] for cam in kw['cameras']}
    def follower():
        tid.append(threading.get_ident())
        return idx.ensure_detection_ticks(date_folder=date, cameras=['Cam2'])
    with patch.object(meta, '_load_params_for_run', return_value={}), patch.object(meta, '_playback_data_dir', return_value=root), patch.object(meta, '_load_day_index_by_camera', side_effect=loader):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(idx.ensure_detection_ticks, date_folder=date, cameras=['Cam1'])
            assert entered.wait(5)
            b = pool.submit(follower)
            deadline, waiting = time.monotonic() + 3, False
            while time.monotonic() < deadline:
                frame = sys._current_frames().get(tid[0]) if tid else None
                while frame:
                    if frame.f_code.co_filename.endswith('singleflight.py') and frame.f_code.co_name == 'do' and frame.f_locals.get('leader') is False:
                        waiting = True
                    frame = frame.f_back
                if waiting: break
                time.sleep(.001)
            release.set()
            first, second = a.result(), b.result()
            assert waiting and 'Cam1' in second and 'Cam2' not in second
    event_date = '2020-04-01'
    (root / 'Events' / event_date / 'Metadata').mkdir(parents=True)
    with patch.object(svc, 'data_dir', return_value=root), patch.object(svc, 'load_event_intervals', return_value=[]) as event_loader:
        for cam in ['EmptyA', 'EmptyB', 'EmptyA', 'EmptyB']:
            idx.ensure_event_intervals(date_folder=event_date, cameras=[cam])
        builds = event_loader.call_count
    assert builds == 4
    return {'detection_leader_keys': list(first), 'detection_follower_requested': 'Cam2', 'detection_follower_keys': list(second), 'alternating_empty_event_queries': 4, 'full_event_rebuilds': builds}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scratch', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='audit-dcfc-', dir=args.scratch) as name:
        root = Path(name).resolve()
        result = {'http': http_probes(root), 'websocket_route': asyncio.run(unrestricted_ws_probe()), 'indexes': index_probes(root)}
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
