import { useEffect, useMemo, useRef, useState } from 'react';
import { streamSnapshotUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Button, Badge } from '../../components/ui';
import { useI18n } from '../../i18n';
import { OverlayCanvas } from '../overlay/OverlayCanvas';
import { useImageLetterbox } from '../overlay/useMediaLetterbox';
import { useRunMetadataWs } from './useRunMetadataWs';

const STALE_SEC = 5;
const LIVE_SNAPSHOT_MS = 3000;
const STALE_SNAPSHOT_BACKOFF_MS = [2000, 4000, 8000];
const ERROR_BACKOFF_MS = [1000, 2000, 4000, 8000];

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

function StatusDot({ mode }: { mode: PreviewMode }) {
  const color =
    mode === 'live'
      ? 'var(--success, #22c55e)'
      : mode === 'stale' || mode === 'error'
        ? 'var(--warning, #f59e0b)'
        : 'var(--text-muted, #888)';
  return (
    <span
      className="camera-status-dot"
      style={{ background: color }}
      aria-hidden="true"
    />
  );
}

export function CameraTile({
  camera,
  useMjpeg,
  active = true,
  gridMode = false,
  onOpen,
  onExpand,
  draggable,
  onDragStart,
  onDrop,
  previewBlobUrl,
  previewWsActive = false,
}: {
  camera: StateCamera;
  useMjpeg: boolean;
  active?: boolean;
  gridMode?: boolean;
  onOpen: () => void;
  onExpand?: () => void;
  draggable?: boolean;
  onDragStart?: () => void;
  onDrop?: () => void;
  previewBlobUrl?: string | null;
  previewWsActive?: boolean;
}) {
  const { t } = useI18n();
  const [snapTs, setSnapTs] = useState(Date.now());
  const [previewError, setPreviewError] = useState(false);
  const [backoffStep, setBackoffStep] = useState(0);
  const [staleSnapStep, setStaleSnapStep] = useState(0);
  const retryTimer = useRef<number | null>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgLoaded, setImgLoaded] = useState(0);

  const mode = useMemo(() => resolvePreviewMode(camera, previewError), [camera, previewError]);
  const running = camera.run_state === 'running';
  // Keep overlays strictly bound to fresh preview frames; stale snapshots can
  // make metadata appear ahead of the person/object by several seconds.
  const wantOverlay = running && active && mode === 'live';
  const meta = useRunMetadataWs(wantOverlay ? camera.run_id : null, camera.source_id ?? null);
  const wantSnapshot = running && active && !useMjpeg && !previewWsActive;
  const wantWsPreview = running && active && !useMjpeg && previewWsActive && previewBlobUrl;

  useEffect(() => {
    setPreviewError(false);
    setBackoffStep(0);
    setStaleSnapStep(0);
  }, [camera.run_id, camera.source_id]);

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
    setImgLoaded((n) => n + 1);
  };

  const snapBase = streamSnapshotUrl(camera.run_id, camera.source_id);
  const snapshotSrc = wantSnapshot
    ? `${snapBase}${snapBase.includes('?') ? '&' : '?'}t=${snapTs}`
    : '';
  const imgSrc = useMjpeg
    ? `/api/v1/runs/${camera.run_id}/stream.mjpg?fps=8${camera.source_id != null ? `&source_id=${camera.source_id}` : ''}`
    : wantWsPreview
      ? previewBlobUrl!
      : snapshotSrc;
  const layoutBox = useImageLetterbox(mediaRef, imgRef, [imgSrc, imgLoaded, camera.run_id, camera.source_id]);

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

  if (gridMode) {
    return (
      <article
        className="camera-card camera-card-mini camera-card-grid"
        draggable={draggable}
        onDragStart={onDragStart}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        onDoubleClick={() => onExpand?.()}
      >
        <div className="camera-card-media" ref={mediaRef} style={{ position: 'relative' }}>
          {mode === 'offline' ? (
            <div className="camera-preview camera-preview-empty">{emptyLabel}</div>
          ) : imgSrc ? (
            <>
              <img
                ref={imgRef}
                src={imgSrc}
                alt={camera.source_name}
                className="camera-preview"
                onError={onImgError}
                onLoad={onImgLoad}
              />
              {wantOverlay ? (
                <OverlayCanvas
                  meta={meta as StreamMetadata | null}
                  layoutBox={layoutBox}
                  density={gridMode ? 'compact' : 'full'}
                />
              ) : null}
            </>
          ) : (
            <div className="camera-preview camera-preview-empty">{emptyLabel}</div>
          )}
          <div className="camera-card-overlay-top">
            <span className="camera-name">{camera.source_name}</span>
            <StatusDot mode={mode} />
          </div>
          <div className="camera-card-overlay-actions">
            {onExpand ? (
              <button
                type="button"
                className="icon-btn"
                title={t('live.expand')}
                onClick={(e) => {
                  e.stopPropagation();
                  onExpand();
                }}
              >
                ⤢
              </button>
            ) : null}
            <button
              type="button"
              className="icon-btn"
              title={t('live.camera.openStream')}
              onClick={(e) => {
                e.stopPropagation();
                onOpen();
              }}
            >
              ↗
            </button>
          </div>
        </div>
      </article>
    );
  }

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
        <div className="camera-preview-wrap" ref={mediaRef} style={{ position: 'relative' }}>
          {imgSrc ? (
            <>
              <img
                ref={imgRef}
                src={imgSrc}
                alt={camera.source_name}
                className="camera-preview"
                onError={onImgError}
                onLoad={onImgLoad}
              />
              {wantOverlay ? (
                <OverlayCanvas
                  meta={meta as StreamMetadata | null}
                  layoutBox={layoutBox}
                  density="full"
                />
              ) : null}
            </>
          ) : (
            <div className="camera-preview camera-preview-empty">{emptyLabel}</div>
          )}
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
