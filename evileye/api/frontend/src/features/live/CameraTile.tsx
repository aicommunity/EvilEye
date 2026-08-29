import { useEffect, useRef, useState } from 'react';
import { streamSnapshotUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Button, Badge } from '../../components/ui';
import { useI18n } from '../../i18n';
import { OverlayCanvas } from '../overlay/OverlayCanvas';
import { useImageLetterbox } from '../overlay/useMediaLetterbox';
import { resolvePreviewMode, type PreviewMode } from './liveHealth';
import { wantLiveSnapshotPoll, wantLiveWsPreview } from './livePreviewPrefer';
import { useRunMetadataWs } from './useRunMetadataWs';

const LIVE_SNAPSHOT_MS = 3000;
const STALE_SNAPSHOT_BACKOFF_MS = [2000, 4000, 8000];
const ERROR_BACKOFF_MS = [1000, 2000, 4000, 8000];

export type { PreviewMode } from './liveHealth';

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
  previewFrameAgeSec,
  camerasPolledAtMs,
  healthTick = 0,
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
  previewFrameAgeSec?: number | null;
  camerasPolledAtMs?: number;
  healthTick?: number;
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

  const [mode, setMode] = useState<PreviewMode>(() =>
    resolvePreviewMode(camera, false, {
      previewFrameAgeSec,
      camerasPolledAtMs,
    }),
  );
  useEffect(() => {
    setMode((prev) =>
      resolvePreviewMode(camera, previewError, {
        previewFrameAgeSec,
        camerasPolledAtMs,
        previousMode: prev,
      }),
    );
  }, [camera, previewError, previewFrameAgeSec, camerasPolledAtMs, healthTick]);
  const running = camera.run_state === 'running';
  // Keep metadata WS subscribed while the run is active so brief stale does not
  // tear down overlays. Hide only on offline / hard error / capture reconnect.
  const wantMetaSub = running && active && mode !== 'offline';
  const showOverlay =
    wantMetaSub && mode !== 'error' && camera.reconnecting !== true && (mode === 'live' || mode === 'stale');
  const overlayDimmed = mode === 'stale';
  const meta = useRunMetadataWs(wantMetaSub ? camera.run_id : null, camera.source_id ?? null);
  // Keep snapshot polling until the first WS blob arrives — otherwise onopen
  // (connected=true) blanks the tile after Live remount from Playback.
  const hasWsFrame = Boolean(previewBlobUrl);
  const wantSnapshot = wantLiveSnapshotPoll({
    running,
    active,
    useMjpeg,
    previewWsActive,
    hasWsFrame,
  });
  const wantWsPreview = wantLiveWsPreview({
    running,
    active,
    useMjpeg,
    previewWsActive,
    hasWsFrame,
  });

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
              {showOverlay ? (
                <OverlayCanvas
                  meta={meta as StreamMetadata | null}
                  layoutBox={layoutBox}
                  density={gridMode ? 'compact' : 'full'}
                  dimmed={overlayDimmed}
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
              {showOverlay ? (
                <OverlayCanvas
                  meta={meta as StreamMetadata | null}
                  layoutBox={layoutBox}
                  density="full"
                  dimmed={overlayDimmed}
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
