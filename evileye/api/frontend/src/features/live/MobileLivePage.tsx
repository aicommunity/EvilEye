import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { stateApi, streamSnapshotUrl, type StateCamera } from '../../api';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Badge, Button } from '../../components/ui';
import { usePolling } from '../../hooks/usePolling';
import { StreamOverlay } from '../../components/StreamOverlay';
import { useI18n } from '../../i18n';

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
  const { t, lang, setLang } = useI18n();
  const [cameras, setCameras] = useState<StateCamera[]>([]);
  const [idx, setIdx] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [snapTs, setSnapTs] = useState(Date.now());

  const load = useCallback(async () => {
    const res = await stateApi.cameras('current');
    setCameras(res.items ?? []);
  }, []);

  usePolling(load, 5000, true, 200);
  useEffect(() => {
    if (idx >= cameras.length) setIdx(0);
  }, [cameras, idx]);

  useEffect(() => {
    if (fullscreen) return;
    const id = window.setInterval(() => setSnapTs(Date.now()), 750);
    return () => window.clearInterval(id);
  }, [fullscreen, idx]);

  const cam = cameras[idx];
  const healthy =
    cam &&
    cam.run_state === 'running' &&
    cam.is_working !== false &&
    cam.preview_available !== false;

  return (
    <div className="mobile-shell">
      <header className="mobile-header">
        <strong>EvilEye</strong>
        <nav>
          <Link to="/m/live">{t('mobile.navLive')}</Link> · <Link to="/m/events">{t('mobile.navEvents')}</Link> ·{' '}
          <Link to="/live">{t('mobile.navDesktop')}</Link>
        </nav>
        <select
          aria-label={t('common.language')}
          value={lang}
          onChange={(e) => setLang(e.target.value === 'en' ? 'en' : 'ru')}
          style={{ marginLeft: 8 }}
        >
          <option value="ru">RU</option>
          <option value="en">EN</option>
        </select>
      </header>
      {!cam ? (
        <p className="empty">{t('mobile.noCameras')}</p>
      ) : (
        <article className="camera-card">
          <div className="camera-card-head">
            <span className="run-name">{cam.source_name}</span>
            <Badge state={cam.run_state}>{cam.run_state}</Badge>
          </div>
          {healthy ? (
            <img
              className="camera-preview"
              style={{ width: '100%', minHeight: 220, objectFit: 'contain', background: '#000' }}
              src={`${streamSnapshotUrl(cam.run_id, cam.source_id)}${streamSnapshotUrl(cam.run_id, cam.source_id).includes('?') ? '&' : '?'}t=${snapTs}`}
              alt={cam.source_name}
            />
          ) : cam.run_state === 'running' ? (
            <div className="camera-preview-empty">{t('live.camera.noSignal')}</div>
          ) : (
            <div className="camera-preview-empty">{t('mobile.stopped')}</div>
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
              {t('mobile.fullscreen')}
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
