import { useEffect, useMemo, useRef, useState } from 'react';
import { streamSnapshotUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Badge, Button } from '../../components/ui';
import { OverlayCanvas } from './OverlayCanvas';
import { useI18n } from '../../i18n';
import { useMjpegLifecycle } from '../../hooks/useMjpegLifecycle';
import { useRunMetadataWs } from './useRunMetadataWs';

const STALE_SEC = 5;
const LIVE_SNAPSHOT_MS = 3000;
const STALE_SNAPSHOT_BACKOFF_MS = [2000, 4000, 8000];
const ERROR_BACKOFF_MS = [1000, 2000, 4000, 8000];
const MJPEG_STALE_POLLS_BEFORE_DROP = 2;

export type PreviewMode = 'live' | 'snapshot' | 'stale' | 'error' | 'offline';

export function resolvePreviewMode(camera: StateCamera, previewError: boolean): PreviewMode {
  if (camera.run_state !== 'running') return 'offline';
  if (previewError) return 'error';
  if (camera.reconnecting === true) return 'stale';
  const age = camera.last_frame_age_sec;
  const staleByAge = age != null && age > STALE_SEC;
  if (camera.preview_available === false || staleByAge || camera.is_working === false) {
    return 'stale';
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
  const [staleSnapStep, setStaleSnapStep] = useState(0);
  const [mjpegHold, setMjpegHold] = useState(false);
  const retryTimer = useRef<number | null>(null);
  const staleMjpegPolls = useRef(0);

  const mode = useMemo(() => resolvePreviewMode(camera, previewError), [camera, previewError]);
  const running = camera.run_state === 'running';
  const wantSnapshot = running && active && !useMjpeg;
  const mjpegCandidate = mode === 'live' && active && useMjpeg && !previewError;

  useEffect(() => {
    setPreviewError(false);
    setBackoffStep(0);
    setStaleSnapStep(0);
    staleMjpegPolls.current = 0;
    setMjpegHold(false);
  }, [camera.run_id, camera.source_id]);

  // Hysteresis: open MJPEG immediately; require 2 consecutive non-candidate polls to drop.
  // Unfocus (useMjpeg=false) drops immediately to avoid leaking the stream.
  useEffect(() => {
    if (!useMjpeg) {
      staleMjpegPolls.current = 0;
      setMjpegHold(false);
      return;
    }
    if (mjpegCandidate) {
      staleMjpegPolls.current = 0;
      setMjpegHold(true);
      return;
    }
    if (!mjpegHold) return;
    staleMjpegPolls.current += 1;
    if (staleMjpegPolls.current >= MJPEG_STALE_POLLS_BEFORE_DROP) {
      setMjpegHold(false);
      staleMjpegPolls.current = 0;
    }
  }, [mjpegCandidate, mjpegHold, useMjpeg, camera.preview_available, camera.is_working, camera.reconnecting, mode]);

  const wantMjpeg = mjpegHold;

  useMjpegLifecycle(wantMjpeg ? camera.run_id : null, camera.source_id);

  const meta = useRunMetadataWs(
    wantMjpeg ? camera.run_id : null,
    camera.source_id,
  );

  useEffect(() => {
    if (!wantSnapshot) return;
    const intervalMs =
      mode === 'live'
        ? LIVE_SNAPSHOT_MS
        : STALE_SNAPSHOT_BACKOFF_MS[Math.min(staleSnapStep, STALE_SNAPSHOT_BACKOFF_MS.length - 1)];
    const id = window.setInterval(() => {
      setSnapTs(Date.now());
      if (mode === 'stale' || mode === 'error') {
        setStaleSnapStep((s) => Math.min(s + 1, STALE_SNAPSHOT_BACKOFF_MS.length - 1));
      }
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [wantSnapshot, mode, staleSnapStep]);

  useEffect(() => {
    return () => {
      if (retryTimer.current != null) window.clearTimeout(retryTimer.current);
    };
  }, []);

  const onImgError = () => {
    setPreviewError(true);
    if (retryTimer.current != null) window.clearTimeout(retryTimer.current);
    const delay = ERROR_BACKOFF_MS[Math.min(backoffStep, ERROR_BACKOFF_MS.length - 1)];
    retryTimer.current = window.setTimeout(() => {
      setPreviewError(false);
      setBackoffStep((s) => Math.min(s + 1, ERROR_BACKOFF_MS.length - 1));
      setSnapTs(Date.now());
    }, delay);
  };

  const onImgLoad = () => {
    setPreviewError(false);
    setBackoffStep(0);
    setStaleSnapStep(0);
  };

  const snapBase = streamSnapshotUrl(camera.run_id, camera.source_id);
  const imgSrc = wantMjpeg
    ? `/api/v1/runs/${camera.run_id}/stream.mjpg?fps=8${camera.source_id != null ? `&source_id=${camera.source_id}` : ''}`
    : wantSnapshot
      ? `${snapBase}${snapBase.includes('?') ? '&' : '?'}t=${snapTs}`
      : '';

  const statusBadge =
    mode === 'offline'
      ? camera.run_state
      : camera.reconnecting
        ? t('live.camera.reconnecting')
        : mode === 'error'
          ? t('live.camera.noSignal')
          : mode === 'stale'
            ? t('live.camera.noPreview')
            : camera.run_state;

  const emptyLabel =
    mode === 'offline'
      ? t('live.camera.stopped')
      : camera.reconnecting
        ? t('live.camera.reconnecting')
        : mode === 'error'
          ? t('live.camera.noSignal')
          : mode === 'stale'
            ? t('live.camera.noPreview')
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
              onLoad={onImgLoad}
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
