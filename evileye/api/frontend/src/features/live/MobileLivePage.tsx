import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { stateApi, streamMjpgUrl, type StateCamera } from '../../api';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Badge, Button } from '../../components/ui';
import { usePolling } from '../../hooks/usePolling';
import { StreamOverlay } from '../../components/StreamOverlay';

export function MobileLivePage() {
  return (
    <AuthProvider>
      <ToastProvider>
        <MobileLiveInner />
      </ToastProvider>
    </AuthProvider>
  );
}

function MobileLiveInner() {
  const [cameras, setCameras] = useState<StateCamera[]>([]);
  const [idx, setIdx] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);

  const load = useCallback(async () => {
    const res = await stateApi.cameras('current');
    setCameras(res.items ?? []);
  }, []);

  usePolling(load, 5000);
  useEffect(() => {
    if (idx >= cameras.length) setIdx(0);
  }, [cameras, idx]);

  const cam = cameras[idx];

  return (
    <div className="mobile-shell">
      <header className="mobile-header">
        <strong>EvilEye</strong>
        <nav>
          <Link to="/m/live">Live</Link> · <Link to="/m/events">Events</Link> · <Link to="/live">Desktop</Link>
        </nav>
      </header>
      {!cam ? (
        <p className="empty">Нет камер</p>
      ) : (
        <article className="camera-card">
          <div className="camera-card-head">
            <span className="run-name">{cam.source_name}</span>
            <Badge state={cam.run_state}>{cam.run_state}</Badge>
          </div>
          {cam.run_state === 'running' ? (
            <img
              className="camera-preview"
              style={{ width: '100%', minHeight: 220, objectFit: 'contain', background: '#000' }}
              src={streamMjpgUrl(cam.run_id, 8, cam.source_id)}
              alt={cam.source_name}
            />
          ) : (
            <div className="camera-preview-empty">Остановлен</div>
          )}
          <div className="toolbar" style={{ marginTop: 12, gap: 8 }}>
            <Button
              size="sm"
              variant="outline"
              style={{ minHeight: 44, minWidth: 44 }}
              disabled={idx <= 0}
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
            >
              ‹
            </Button>
            <span className="hint">
              {idx + 1}/{cameras.length}
            </span>
            <Button
              size="sm"
              variant="outline"
              style={{ minHeight: 44, minWidth: 44 }}
              disabled={idx >= cameras.length - 1}
              onClick={() => setIdx((i) => Math.min(cameras.length - 1, i + 1))}
            >
              ›
            </Button>
            <Button
              size="sm"
              variant="primary"
              style={{ minHeight: 44 }}
              disabled={cam.run_state !== 'running'}
              onClick={() => setFullscreen(true)}
            >
              Полный экран
            </Button>
          </div>
        </article>
      )}
      {fullscreen && cam ? (
        <StreamOverlay rid={cam.run_id} sourceId={cam.source_id} onClose={() => setFullscreen(false)} />
      ) : null}
    </div>
  );
}
