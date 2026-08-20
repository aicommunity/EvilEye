import { useEffect, useMemo, useRef, useState } from 'react';
import type { FrameSize, PlaybackCamera, PlaybackDetectionItem, PlaybackEventInterval, PlaybackPlayMode } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { prepareOverlayMetadata } from '../overlay/overlayMath';
import { resolvePlaybackFrameSize } from '../overlay/playbackFrameSize';
import { useMediaLetterbox } from '../overlay/useMediaLetterbox';
import { useI18n } from '../../i18n';
import { PlaybackBusyHint } from './PlaybackBusyHint';
import { usePlaybackCameraMetadata } from './PlaybackCameraView';
import { seekPlaybackVideo, shouldEmitPlaybackClock } from './playbackVideoSync';

export function SplitPlaybackCell({
  videoUrl,
  srcCoords,
  label,
  cameraId,
  camera,
  sourceId: _sourceId,
  getPosition,
  positionSec,
  playing,
  speed,
  startTs,
  runId,
  showMetadata,
  playMode = 'normal',
  scrubbing = false,
  detectionItems = [],
  globalDetectionTs = [],
  eventIntervals = [],
  onVideoClock,
  onExpand,
  expanded = false,
  frameSize: frameSizeProp,
  onFrameSize,
  detectionsReady = true,
}: {
  videoUrl: string;
  srcCoords: [number, number, number, number];
  label: string;
  cameraId: string;
  camera?: PlaybackCamera;
  sourceId?: number | null;
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
  startTs: number;
  runId: number | null;
  showMetadata: boolean;
  playMode?: PlaybackPlayMode;
  scrubbing?: boolean;
  detectionItems?: PlaybackDetectionItem[];
  globalDetectionTs?: number[];
  eventIntervals?: PlaybackEventInterval[];
  onVideoClock?: (globalSec: number) => void;
  onExpand?: () => void;
  expanded?: boolean;
  frameSize?: FrameSize | null;
  onFrameSize?: (size: FrameSize) => void;
  detectionsReady?: boolean;
}) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;
  const [videoReady, setVideoReady] = useState(0);
  const [seeking, setSeeking] = useState(false);
  const [videoGlobalSec, setVideoGlobalSec] = useState<number | null>(null);
  const [localFrameSize, setLocalFrameSize] = useState<FrameSize | null>(null);
  const parentVideoSize = frameSizeProp ?? localFrameSize;
  const onVideoClockRef = useRef(onVideoClock);
  onVideoClockRef.current = onVideoClock;

  const metadataFrameSize = useMemo(
    () => resolvePlaybackFrameSize(camera, parentVideoSize),
    [camera, parentVideoSize],
  );

  const { meta: mergedMeta, loading: metaLoading } = usePlaybackCameraMetadata({
    cameraId,
    camera,
    positionSec,
    runId,
    showMetadata,
    hasVideo: Boolean(videoUrl),
    frameSize: metadataFrameSize,
    playing,
    scrubbing,
    videoGlobalSec,
    videoSeeking: seeking,
    detectionItems,
    globalDetectionTs,
    eventIntervals,
    detectionsReady,
  });

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
    return prepareOverlayMetadata(mergedMeta, metadataFrameSize);
  }, [mergedMeta, showMetadata, metadataFrameSize]);

  useEffect(() => {
    setLocalFrameSize(null);
    setVideoReady(0);
    setVideoGlobalSec(null);
  }, [videoUrl]);

  const drawFrame = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    if (video.readyState < 2) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const cw = canvas.width;
    const ch = canvas.height;
    if (cw <= 0 || ch <= 0) return;
    const [sx, sy, sw, sh] = srcCoords;
    try {
      ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch);
    } catch {
      /* frame not ready */
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const onFrame = () => drawFrame();
    video.addEventListener('loadeddata', onFrame);
    video.addEventListener('seeked', onFrame);
    video.addEventListener('canplay', onFrame);

    const videoWithVfc = video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
      cancelVideoFrameCallback?: (h: number) => void;
    };
    let vfcHandle = 0;
    if (playing && videoWithVfc.requestVideoFrameCallback) {
      const loop = () => {
        drawFrame();
        vfcHandle = videoWithVfc.requestVideoFrameCallback!(loop);
      };
      vfcHandle = videoWithVfc.requestVideoFrameCallback(loop);
    } else {
      video.addEventListener('timeupdate', onFrame);
    }

    drawFrame();
    return () => {
      video.removeEventListener('timeupdate', onFrame);
      video.removeEventListener('loadeddata', onFrame);
      video.removeEventListener('seeked', onFrame);
      video.removeEventListener('canplay', onFrame);
      if (vfcHandle && videoWithVfc.cancelVideoFrameCallback) {
        try {
          videoWithVfc.cancelVideoFrameCallback(vfcHandle);
        } catch {
          /* ignore */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, srcCoords, playMode, playing, videoReady]);

  useEffect(() => {
    const container = mediaRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const ro = new ResizeObserver(() => {
      const rect = container.getBoundingClientRect();
      const [, , sw, sh] = srcCoords;
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
      drawFrame();
    });
    ro.observe(container);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [srcCoords]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
    if (playing) void video.play().catch(() => null);
    else video.pause();
  }, [playing, speed, videoUrl]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onSeeking = () => setSeeking(true);
    const onSeeked = () => {
      setSeeking(false);
      setVideoGlobalSec(startTs + video.currentTime);
    };
    const onTime = () => {
      if (video.readyState >= 2) setVideoGlobalSec(startTs + video.currentTime);
      if (video.seeking || scrubbing) return;
      if (playing && shouldEmitPlaybackClock(cameraId, video)) {
        onVideoClockRef.current?.(startTs + video.currentTime);
      }
    };
    video.addEventListener('seeking', onSeeking);
    video.addEventListener('seeked', onSeeked);
    video.addEventListener('timeupdate', onTime);
    setSeeking(video.seeking);
    return () => {
      video.removeEventListener('seeking', onSeeking);
      video.removeEventListener('seeked', onSeeked);
      video.removeEventListener('timeupdate', onTime);
    };
  }, [videoUrl, playing, scrubbing, startTs, cameraId]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !videoUrl) return;
    seekPlaybackVideo(video, getPositionRef.current(), startTs, {
      playing,
      scrubbing,
      thresholdSec: playing && !scrubbing ? 0.35 : undefined,
    });
    const videoWithVfc = video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
    };
    if (!playing && videoWithVfc.requestVideoFrameCallback) {
      videoWithVfc.requestVideoFrameCallback(() => drawFrame());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec, videoUrl, startTs, playing, scrubbing]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  const inner = (
    <div ref={mediaRef} className="split-playback-container" style={{ position: 'relative' }}>
      <video
        ref={videoRef}
        src={videoUrl}
        preload="auto"
        className="split-playback-video"
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
          seekPlaybackVideo(video, getPositionRef.current(), startTs, {
            playing,
            scrubbing,
            thresholdSec: playing && !scrubbing ? 0.35 : undefined,
          });
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
        visible={showMetadata && !seeking}
        renderMode="playback"
      />
      <PlaybackBusyHint
        seeking={seeking}
        loading={metaLoading}
        hasObjects={(displayMeta?.objects?.length ?? 0) > 0}
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
