import { useEffect, useMemo, useRef, useState } from 'react';
import { streamSnapshotUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Badge, Button } from '../../components/ui';
import { OverlayCanvas } from './OverlayCanvas';
import { useI18n } from '../../i18n';
import { useMjpegLifecycle } from '../../hooks/useMjpegLifecycle';
import { useRunMetadataWs } from './useRunMetadataWs';

const STALE_SEC = 5;
const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000];

type PreviewMode = 'live' | 'snapshot' | 'stale' | 'error' | 'offline';

function resolvePreviewMode(camera: StateCamera, previewError: boolean): PreviewMode {
  if (camera.run_state !== 'running') return 'offline';
  if (previewError) return 'error';
  const age = camera.last_frame_age_sec;
  const staleByAge = age != null && age > STALE_SEC;
  if (camera.is_working === false || staleByAge || camera.preview_available === false) {
    return camera.reconnecting ? 'stale' : 'stale';
  }
  return 'live';
}

export function CameraTile({
  camera,
  useMjpeg,
  active = true,
  onOpen,
  draggable,
  onDragStart,
  onDrop,
}: {
  camera: StateCamera;
  useMjpeg: boolean;
  active?: boolean;
  onOpen: () => void;
  draggable?: boolean;
  onDragStart?: () => void;
  onDrop?: () => void;
}) {
  const { t } = useI18n();
  const [snapTs, setSnapTs] = useState(Date.now());
  const [previewError, setPreviewError] = useState(false);
  const [backoffStep, setBackoffStep] = useState(0);
  const retryTimer = useRef<number | null>(null);

  const mode = useMemo(() => resolvePreviewMode(camera, previewError), [camera, previewError]);
  const canStream = mode === 'live' && active;
  const wantMjpeg = canStream && useMjpeg;

  useMjpegLifecycle(wantMjpeg ? camera.run_id : null, camera.source_id);

  const meta = useRunMetadataWs(
    wantMjpeg ? camera.run_id : null,
    camera.source_id,
  );

  useEffect(() => {
    setPreviewError(false);
    setBackoffStep(0);
  }, [camera.run_id, camera.source_id, camera.is_working, camera.preview_available]);

  useEffect(() => {
    if (!canStream || useMjpeg || previewError) return;
    const id = window.setInterval(() => setSnapTs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [canStream, useMjpeg, previewError]);

  useEffect(() => {
    return () => {
      if (retryTimer.current != null) window.clearTimeout(retryTimer.current);
    };
  }, []);

  const onImgError = () => {
    setPreviewError(true);
    if (retryTimer.current != null) window.clearTimeout(retryTimer.current);
    const delay = BACKOFF_STEPS_MS[Math.min(backoffStep, BACKOFF_STEPS_MS.length - 1)];
    retryTimer.current = window.setTimeout(() => {
      setPreviewError(false);
      setBackoffStep((s) => Math.min(s + 1, BACKOFF_STEPS_MS.length - 1));
      setSnapTs(Date.now());
    }, delay);
  };

  const imgSrc =
    canStream
      ? useMjpeg
        ? `/api/v1/runs/${camera.run_id}/stream.mjpg?fps=8${camera.source_id != null ? `&source_id=${camera.source_id}` : ''}`
        : `${streamSnapshotUrl(camera.run_id, camera.source_id)}${streamSnapshotUrl(camera.run_id, camera.source_id).includes('?') ? '&' : '?'}t=${snapTs}`
      : '';

  const statusBadge =
    mode === 'offline'
      ? camera.run_state
      : mode === 'error' || mode === 'stale'
        ? camera.reconnecting
          ? t('live.camera.reconnecting')
          : t('live.camera.noSignal')
        : camera.run_state;

  const emptyLabel =
    mode === 'offline'
      ? t('live.camera.stopped')
      : mode === 'error'
        ? t('live.camera.noSignal')
        : mode === 'stale'
          ? camera.reconnecting
            ? t('live.camera.reconnecting')
            : t('live.camera.stale')
          : t('live.camera.outOfView');

  return (
    <article
      className="camera-card"
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <div className="camera-card-head">
        <span className="run-name">{camera.source_name}</span>
        <Badge state={mode === 'live' ? camera.run_state : 'stopped'}>{statusBadge}</Badge>
      </div>
      <p className="hint">
        {t('live.camera.runLabel', { id: camera.run_id, sid: camera.source_id ?? '—' })}
      </p>
      {mode === 'offline' ? (
        <div className="camera-preview camera-preview-empty">{emptyLabel}</div>
      ) : (
        <div className="camera-preview-wrap" style={{ position: 'relative' }}>
          {imgSrc ? (
            <img
              src={imgSrc}
              alt={camera.source_name}
              className="camera-preview"
              onError={onImgError}
            />
          ) : (
            <div className="camera-preview camera-preview-empty">{emptyLabel}</div>
          )}
          {wantMjpeg ? <OverlayCanvas meta={meta as StreamMetadata | null} /> : null}
        </div>
      )}
      <div className="camera-actions">
        <Button size="sm" variant="outline" disabled={mode === 'offline'} onClick={onOpen}>
          {t('live.camera.openStream')}
        </Button>
      </div>
    </article>
  );
}
