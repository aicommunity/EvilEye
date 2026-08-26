import { useEffect, useMemo, useRef, useState } from 'react';
import type { FrameSize, PlaybackCamera, PlaybackDetectionItem, PlaybackEventInterval, PlaybackPlayMode } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { prepareOverlayMetadata } from '../overlay/overlayMath';
import { resolvePlaybackFrameSize } from '../overlay/playbackFrameSize';
import { useMediaLetterbox } from '../overlay/useMediaLetterbox';
import { useI18n } from '../../i18n';
import { PlaybackBusyHint } from './PlaybackBusyHint';
import { usePlaybackCameraMetadata } from './PlaybackCameraView';
import { playbackDebugInc } from './playbackDebug';
import { seekPlaybackVideo, seekingAgeMs, SEEKING_STUCK_MS, shouldEmitPlaybackClock } from './playbackVideoSync';
import { drainVideoElement, reloadVideoMedia } from './drainVideo';

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
  mediaEpoch: mediaEpochProp = 0,
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
  mediaEpoch?: number;
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
  const [localEpoch, setLocalEpoch] = useState(0);
  const mediaEpoch = mediaEpochProp + localEpoch;
  const parentVideoSize = frameSizeProp ?? localFrameSize;
  const onVideoClockRef = useRef(onVideoClock);
  onVideoClockRef.current = onVideoClock;
  const playingRef = useRef(playing);
  playingRef.current = playing;
  const scrubbingRef = useRef(scrubbing);
  scrubbingRef.current = scrubbing;
  const startTsRef = useRef(startTs);
  startTsRef.current = startTs;

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
    if (playing && !scrubbing) {
      playbackDebugInc('playCalls');
      void video.play().catch(() => playbackDebugInc('playRejects'));
    } else {
      if (scrubbing) playbackDebugInc('pauseFromScrub');
      video.pause();
    }
  }, [playing, scrubbing, speed, videoUrl]);

  useEffect(() => {
    if (scrubbing) return;
    const video = videoRef.current;
    if (!video) return;
    let stuckAttempts = 0;
    let pausedZombieTicks = 0;
    const timer = window.setInterval(() => {
      if (playingRef.current && !scrubbingRef.current && video.paused) {
        pausedZombieTicks += 1;
        playbackDebugInc('playCalls');
        void video.play().catch(() => playbackDebugInc('playRejects'));
        if (pausedZombieTicks === 2) {
          seekPlaybackVideo(video, getPositionRef.current(), startTs, {
            playing: true,
            force: true,
            scrubbing: true,
            thresholdSec: 0,
            segmentEndTs:
              Number.isFinite(video.duration) && video.duration > 0 ? startTs + video.duration : undefined,
          });
          drawFrame();
        }
        if (pausedZombieTicks >= 6 && video.readyState < 2) {
          reloadVideoMedia(video);
        }
        return;
      }
      pausedZombieTicks = 0;
      if (video.seeking && seekingAgeMs(video) >= SEEKING_STUCK_MS) {
        playbackDebugInc('seekingStuckRecoveries');
        stuckAttempts += 1;
        setSeeking(false);
        seekPlaybackVideo(video, getPositionRef.current(), startTs, {
          playing: playingRef.current,
          force: true,
          scrubbing: true,
          thresholdSec: 0,
          segmentEndTs:
            Number.isFinite(video.duration) && video.duration > 0 ? startTs + video.duration : undefined,
        });
        drawFrame();
        if (stuckAttempts === 2 || stuckAttempts >= 4) {
          reloadVideoMedia(video);
        }
        return;
      }
      if (!playingRef.current && video.readyState < 2) {
        stuckAttempts += 1;
        if (stuckAttempts >= 3) {
          stuckAttempts = 0;
          reloadVideoMedia(video);
          drawFrame();
        }
      } else if (!video.seeking) {
        stuckAttempts = 0;
      }
    }, 700);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrubbing, playing, videoUrl, startTs, mediaEpoch]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onSeeking = () => setSeeking(true);
    const onSeeked = () => {
      setSeeking(false);
      const st = startTsRef.current;
      setVideoGlobalSec(st + video.currentTime);
      // Pin after load even while scrubbing (new segment src starts at t=0 otherwise).
      seekPlaybackVideo(video, getPositionRef.current(), st, {
        playing: playingRef.current,
        scrubbing: scrubbingRef.current,
        thresholdSec: playingRef.current && !scrubbingRef.current ? 1.0 : undefined,
        segmentEndTs:
          Number.isFinite(video.duration) && video.duration > 0 ? st + video.duration : undefined,
      });
      if (playingRef.current && !scrubbingRef.current && video.paused) {
        void video.play().catch(() => null);
      }
      drawFrame();
      const videoWithVfc = video as HTMLVideoElement & {
        requestVideoFrameCallback?: (cb: () => void) => number;
      };
      videoWithVfc.requestVideoFrameCallback?.(() => drawFrame());
    };
    const onTime = () => {
      const st = startTsRef.current;
      if (video.readyState >= 2) setVideoGlobalSec(st + video.currentTime);
      if (video.seeking || scrubbingRef.current) return;
      if (playingRef.current && shouldEmitPlaybackClock(cameraId, video)) {
        onVideoClockRef.current?.(st + video.currentTime);
      }
    };
    const onError = () => {
      setSeeking(false);
      playbackDebugInc('playRejects');
      const el = video;
      window.setTimeout(() => {
        if (videoRef.current !== el || !videoUrl) return;
        if (reloadVideoMedia(el)) {
          seekPlaybackVideo(el, getPositionRef.current(), startTsRef.current, {
            playing: playingRef.current,
            scrubbing: scrubbingRef.current,
            force: true,
            thresholdSec: 0,
            segmentEndTs:
              Number.isFinite(el.duration) && el.duration > 0
                ? startTsRef.current + el.duration
                : undefined,
          });
          drawFrame();
        }
      }, 400);
    };
    video.addEventListener('seeking', onSeeking);
    video.addEventListener('seeked', onSeeked);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('loadeddata', onSeeked);
    video.addEventListener('error', onError);
    setSeeking(video.seeking);
    return () => {
      video.removeEventListener('seeking', onSeeking);
      video.removeEventListener('seeked', onSeeked);
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('loadeddata', onSeeked);
      video.removeEventListener('error', onError);
    };
  }, [videoUrl, cameraId, mediaEpoch]);

  useEffect(() => {
    const el = videoRef;
    return () => {
      drainVideoElement(el.current);
    };
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !videoUrl) return;
    const stuck = video.seeking && seekingAgeMs(video) >= SEEKING_STUCK_MS;
    if (video.seeking && !scrubbing && !stuck) return;
    // Settle/drag: finish the current seek before issuing another Range.
    if (scrubbing && video.seeking && !stuck) return;
    seekPlaybackVideo(video, getPositionRef.current(), startTs, {
      playing,
      scrubbing,
      force: stuck,
      thresholdSec: playing && !scrubbing ? 1.0 : undefined,
      segmentEndTs:
        Number.isFinite(video.duration) && video.duration > 0 ? startTs + video.duration : undefined,
    });
    const videoWithVfc = video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
    };
    // Always paint after pin — paused archive otherwise stays on a black first frame.
    const paint = () => drawFrame();
    if (videoWithVfc.requestVideoFrameCallback) {
      videoWithVfc.requestVideoFrameCallback(paint);
    } else {
      paint();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec, videoUrl, startTs, playing, scrubbing, mediaEpoch]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  const inner = (
    <div ref={mediaRef} className="split-playback-container" style={{ position: 'relative' }}>
      <video
        key={`split-media-${mediaEpoch}`}
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
            thresholdSec: playing && !scrubbing ? 1.0 : undefined,
            segmentEndTs:
              video && Number.isFinite(video.duration) && video.duration > 0
                ? startTs + video.duration
                : undefined,
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
        visible={showMetadata}
        renderMode="playback"
      />
      <PlaybackBusyHint
        seeking={seeking}
        loading={metaLoading}
        hasObjects={(displayMeta?.objects?.length ?? 0) > 0}
      />
      {!showMetadata ? <div className="live-overlay-source">{label}</div> : null}
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
