import { useEffect, useMemo, useRef, useState } from 'react';
import type { FrameSize } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { transformMetadataForCrop } from '../overlay/overlayMath';
import { useMediaLetterbox } from '../overlay/useMediaLetterbox';
import { useI18n } from '../../i18n';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';
import { seekPlaybackVideo } from './playbackVideoSync';
import { usePlaybackMetadata } from './usePlaybackMetadata';
import { usePlaybackStaticMetadata } from './usePlaybackStaticMetadata';

export function SplitPlaybackCell({
  videoUrl,
  srcCoords,
  label,
  cameraId,
  sourceId,
  getPosition,
  positionSec,
  playing,
  speed,
  startTs,
  runId,
  showMetadata,
  onExpand,
  expanded = false,
  frameSize: frameSizeProp,
  onFrameSize,
}: {
  videoUrl: string;
  srcCoords: [number, number, number, number];
  label: string;
  cameraId: string;
  sourceId?: number | null;
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
  startTs: number;
  runId: number | null;
  showMetadata: boolean;
  onExpand?: () => void;
  expanded?: boolean;
  frameSize?: FrameSize | null;
  onFrameSize?: (size: FrameSize) => void;
}) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;
  const [videoReady, setVideoReady] = useState(0);
  const [localFrameSize, setLocalFrameSize] = useState<FrameSize | null>(null);
  const parentVideoSize = frameSizeProp ?? localFrameSize;

  const staticMeta = usePlaybackStaticMetadata({
    camera: cameraId,
    sourceId,
    runId,
    enabled: showMetadata,
    frameSize: parentVideoSize,
  });
  const { meta: dynamicMeta } = usePlaybackMetadata({
    camera: cameraId,
    sourceId,
    positionSec,
    runId,
    enabled: showMetadata,
    frameSize: parentVideoSize,
  });
  const mergedMeta = useMemo(
    () => mergePlaybackMetadata(staticMeta, dynamicMeta),
    [staticMeta, dynamicMeta],
  );

  const layoutBox = useMediaLetterbox(
    mediaRef,
    canvasRef,
    () => {
      const canvas = canvasRef.current;
      if (!canvas?.width) return null;
      return { w: canvas.width, h: canvas.height };
    },
    [videoReady, videoUrl, srcCoords],
  );

  const displayMeta = useMemo(() => {
    if (!mergedMeta || !showMetadata) return null;
    const parentW = parentVideoSize?.w ?? 0;
    const parentH = parentVideoSize?.h ?? 0;
    if (parentW <= 0 || parentH <= 0) return mergedMeta;
    return transformMetadataForCrop(mergedMeta, srcCoords, parentW, parentH);
  }, [mergedMeta, showMetadata, srcCoords, parentVideoSize]);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const [sx, sy, sw, sh] = srcCoords;
    const draw = () => {
      if (video.readyState < 2) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const cw = canvas.width;
      const ch = canvas.height;
      if (cw <= 0 || ch <= 0) return;
      ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch);
    };

    video.addEventListener('timeupdate', draw);
    video.addEventListener('loadeddata', draw);
    video.addEventListener('seeked', draw);
    draw();
    return () => {
      video.removeEventListener('timeupdate', draw);
      video.removeEventListener('loadeddata', draw);
      video.removeEventListener('seeked', draw);
    };
  }, [videoUrl, srcCoords]);

  useEffect(() => {
    const container = mediaRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const ro = new ResizeObserver(() => {
      const rect = container.getBoundingClientRect();
      const [,, sw, sh] = srcCoords;
      const aspect = sw / sh;
      let w = rect.width;
      let h = w / aspect;
      if (h > rect.height) {
        h = rect.height;
        w = h * aspect;
      }
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      canvas.width = Math.max(1, Math.round(w));
      canvas.height = Math.max(1, Math.round(h));
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [srcCoords]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
    if (playing) void video.play().catch(() => null);
    else video.pause();
  }, [playing, speed, videoUrl]);

  useEffect(() => {
    let raf = 0;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      const video = videoRef.current;
      if (video && videoUrl) {
        seekPlaybackVideo(video, getPositionRef.current(), startTs, { playing });
      }
      if (playing) raf = window.requestAnimationFrame(tick);
    };
    tick();
    return () => {
      cancelled = true;
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, [playing, videoUrl, startTs, positionSec]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  const inner = (
    <div ref={mediaRef} className="split-playback-container" style={{ position: 'relative' }}>
      <video
        ref={videoRef}
        src={videoUrl}
        preload="auto"
        style={{ display: 'none' }}
        muted
        playsInline
        onLoadedMetadata={() => {
          const video = videoRef.current;
          if (video?.videoWidth && video.videoHeight) {
            const size = { w: video.videoWidth, h: video.videoHeight };
            setLocalFrameSize(size);
            onFrameSize?.(size);
          }
          setVideoReady((n) => n + 1);
          seekPlaybackVideo(video, getPositionRef.current(), startTs, { playing });
        }}
      />
      <canvas
        ref={canvasRef}
        className={previewClass}
        onDoubleClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onExpand?.();
        }}
      />
      <MetadataOverlayLayer
        meta={displayMeta}
        layoutBox={layoutBox.width > 0 && layoutBox.height > 0 ? layoutBox : undefined}
        density={expanded ? 'full' : 'compact'}
        visible={showMetadata}
      />
      <div className="camera-card-overlay-top">
        <span className="camera-name">{label}</span>
      </div>
      {onExpand ? (
        <div className="camera-card-overlay-actions">
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
        </div>
      ) : null}
    </div>
  );

  if (expanded) return inner;

  return (
    <article className="camera-card camera-card-mini camera-card-grid playback-cell" onDoubleClick={onExpand}>
      <div className="camera-card-media" style={{ position: 'relative' }}>
        {inner}
      </div>
    </article>
  );
}
