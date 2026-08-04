import { useEffect, useState } from 'react';
import { runGet, streamMjpgUrl, streamStatus } from '../api';
import { useMjpegLifecycle } from '../hooks/useMjpegLifecycle';
import { useI18n } from '../i18n';
import { Button, Badge } from './ui';

export function StreamOverlay({
  rid,
  sourceId,
  onClose,
}: {
  rid: number;
  sourceId?: number | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [fps, setFps] = useState(10);
  const [name, setName] = useState('…');
  const [state, setState] = useState('…');
  const [statusText, setStatusText] = useState('…');
  const [src, setSrc] = useState(() => streamMjpgUrl(rid, 10, sourceId ?? null));

  useMjpegLifecycle(rid, sourceId ?? null);

  useEffect(() => {
    setSrc(streamMjpgUrl(rid, fps, sourceId ?? null));
  }, [rid, sourceId, fps]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const run = await runGet(rid);
        if (cancelled) return;
        if (run.state !== 'running') {
          onClose();
          return;
        }
        setName(run.name ?? t('live.stream.runName', { id: run.id }));
        setState(run.state);
        const st = await streamStatus(rid, sourceId ?? null).catch(() => null);
        if (cancelled || !st) return;
        setStatusText(
          st.stream_active
            ? t('live.stream.viewerActive')
            : st.has_frame
              ? t('live.stream.frameReady')
              : !st.frame_dir_configured
                ? t('live.stream.noPreview')
                : !st.web_stream_available
                  ? t('live.stream.unavailable')
                  : t('live.stream.noFrame'),
        );
      } catch {
        /* ignore */
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [rid, sourceId, onClose, t]);

  return (
    <div className="stream-container open">
      <div className="stream-header">
        <div className="stream-info">
          <span>
            {t('live.stream.titleRun')} <strong>{rid}</strong>
            {sourceId != null ? ` · source ${sourceId}` : ''}
          </span>
          <span className="stream-name">{name}</span>
          <Badge state={state}>{state}</Badge>
          <span className="stream-status">{statusText}</span>
        </div>
        <div className="stream-controls">
          <label className="stream-fps-label">
            FPS{' '}
            <input
              type="number"
              min={1}
              max={30}
              value={fps}
              onChange={(e) => setFps(Math.max(1, Math.min(30, Number(e.target.value) || 10)))}
            />
          </label>
        </div>
        <div className="stream-actions">
          <Button variant="outline" onClick={onClose}>
            {t('live.stream.close')}
          </Button>
        </div>
      </div>
      <div className="stream-body">
        <div className="stream-main">
          <p className="stream-main-title">{t('live.stream.title')}</p>
          <img src={src} alt={t('live.stream.title')} className="stream-frame" />
        </div>
      </div>
    </div>
  );
}
