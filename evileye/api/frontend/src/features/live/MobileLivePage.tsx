import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { stateApi, streamSnapshotUrl, streamStatus, type StateCamera, cacheGet, cacheSet, isAbortError } from '../../api';
import { Badge, Button } from '../../components/ui';
import { useVisibilityPolling } from '../../hooks/useVisibilityPolling';
import { StreamOverlay } from '../../components/StreamOverlay';
import { useI18n } from '../../i18n';

export function MobileLivePage() {
  return <MobileLiveInner />;
}

function MobileLiveInner() {
  const { t, lang, setLang } = useI18n();
  const cached = cacheGet<{ items: StateCamera[] }>('state:cameras:current');
  const [cameras, setCameras] = useState<StateCamera[]>(() => cached?.items ?? []);
  const [camerasLoading, setCamerasLoading] = useState(() => !(cached?.items?.length));
  const [idx, setIdx] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [snapTs, setSnapTs] = useState(Date.now());
  const abortRef = useRef<AbortController | null>(null);
  const camerasLoadingTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    if (camerasLoadingTimerRef.current != null) {
      window.clearTimeout(camerasLoadingTimerRef.current);
      camerasLoadingTimerRef.current = null;
    }
    setCameras((prev) => {
      if (!prev.length) {
        camerasLoadingTimerRef.current = window.setTimeout(() => setCamerasLoading(true), 1500);
      }
      return prev;
    });
    try {
      const res = await stateApi.cameras('current', { signal: ac.signal });
      if (ac.signal.aborted) return;
      cacheSet('state:cameras:current', res, 12_000);
      setCameras(res.items ?? []);
    } catch (e) {
      if (isAbortError(e)) return;
    } finally {
      if (camerasLoadingTimerRef.current != null) {
        window.clearTimeout(camerasLoadingTimerRef.current);
        camerasLoadingTimerRef.current = null;
      }
      if (!ac.signal.aborted) setCamerasLoading(false);
    }
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => () => {
    if (camerasLoadingTimerRef.current != null) {
      window.clearTimeout(camerasLoadingTimerRef.current);
      camerasLoadingTimerRef.current = null;
    }
  }, []);

  useVisibilityPolling(load, 15_000, true, 200);
  useEffect(() => {
    if (idx >= cameras.length) setIdx(0);
  }, [cameras, idx]);

  const cam = cameras[idx];
  const running = cam?.run_state === 'running';
  const showSnapshot = Boolean(running);

  useEffect(() => {
    if (fullscreen || !showSnapshot) return;
    const stale =
      cam &&
      (cam.preview_available === false ||
        cam.is_working === false ||
        cam.reconnecting === true ||
        (cam.last_frame_age_sec != null && cam.last_frame_age_sec > 5));
    const intervalMs = stale ? 2000 : 750;
    const id = window.setInterval(() => setSnapTs(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [fullscreen, idx, showSnapshot, cam]);

  useEffect(() => {
    if (!cam || cam.run_state !== 'running') return;
    const rid = cam.run_id;
    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void streamStatus(rid, null).catch(() => undefined);
    };
    tick();
    const id = window.setInterval(tick, 5_000);
    return () => window.clearInterval(id);
  }, [cam?.run_id, cam?.run_state]);

  const emptyLabel = !cam
    ? null
    : cam.reconnecting
      ? t('live.camera.reconnecting')
      : cam.run_state !== 'running'
        ? t('mobile.stopped')
        : t('live.camera.noPreview');

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
        <p className="empty">{camerasLoading ? t('common.searching') : t('mobile.noCameras')}</p>
      ) : (
        <article className="camera-card">
          <div className="camera-card-head">
            <span className="run-name">{cam.source_name}</span>
            <Badge state={cam.run_state}>
              {cam.reconnecting ? t('live.camera.reconnecting') : cam.run_state}
            </Badge>
          </div>
          {showSnapshot ? (
            <img
              className="camera-preview"
              style={{ width: '100%', minHeight: 220, objectFit: 'contain', background: '#000' }}
              src={`${streamSnapshotUrl(cam.run_id, cam.source_id)}${streamSnapshotUrl(cam.run_id, cam.source_id).includes('?') ? '&' : '?'}t=${snapTs}`}
              alt={cam.source_name}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.opacity = '0.3';
              }}
              onLoad={(e) => {
                (e.currentTarget as HTMLImageElement).style.opacity = '1';
              }}
            />
          ) : (
            <div className="camera-preview-empty">{emptyLabel}</div>
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
