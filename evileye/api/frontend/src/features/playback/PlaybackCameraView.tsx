import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import {
  playbackApi,
  type FrameSize,
  type PlaybackCamera,
  type PlaybackDetectionItem,
  type PlaybackPlayMode,
  type PlaybackSegment,
  type StreamMetadata,
} from '../../api';
import { useI18n } from '../../i18n';
import {
  hasActiveTrackAt,
  objectsFromDetectionIndex,
  objectsToOverlayFromIndex,
  overlayTimeLabel,
  shouldShowPlaybackObjects,
} from './detectionSync';
import { PlaybackBusyHint } from './PlaybackBusyHint';
import { PlaybackMediaWithOverlay } from './PlaybackMediaWithOverlay';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';
import { seekPlaybackVideo, shouldEmitPlaybackClock } from './playbackVideoSync';
import { usePlaybackMetadata } from './usePlaybackMetadata';
import { usePlaybackStaticMetadata } from './usePlaybackStaticMetadata';
import { pickSegmentNear } from './timelineMath';

export type PlaybackMediaSlot = {
  url: string | null;
  startTs: number;
  endTs: number;
};

function nextSegment(segs: PlaybackSegment[], current: PlaybackSegment | null): PlaybackSegment | null {
  if (!current || !segs.length) return null;
  const idx = segs.findIndex((s) => s.path === current.path);
  if (idx < 0 || idx >= segs.length - 1) return null;
  return segs[idx + 1];
}

export function usePlaybackCameraSlot(
  segments: PlaybackSegment[],
  getPosition: () => number,
  positionSec: number,
  playing: boolean,
  playMode: PlaybackPlayMode = 'normal',
  scrubbing = false,
  onVideoClock?: (globalSec: number) => void,
  clockId?: string,
) {
  const ref = useRef<HTMLVideoElement>(null);
  const preloadRef = useRef<HTMLVideoElement>(null);
  const pathRef = useRef<string | null>(null);
  const slotRef = useRef<PlaybackMediaSlot | null>(null);
  const [slot, setSlot] = useState<PlaybackMediaSlot | null>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;
  const segmentsRef = useRef(segments);
  segmentsRef.current = segments;
  const scrubbingRef = useRef(scrubbing);
  scrubbingRef.current = scrubbing;
  const onVideoClockRef = useRef(onVideoClock);
  onVideoClockRef.current = onVideoClock;

  const applySync = () => {
    const position = getPositionRef.current();
    const segs = segmentsRef.current;
    const seg = pickSegmentNear(segs, position);
    const nxt = nextSegment(segs, seg);
    const preload = preloadRef.current;
    let segmentChanged = false;

    if (!seg) {
      if (pathRef.current != null) {
        pathRef.current = null;
        slotRef.current = null;
        setSlot(null);
      }
    } else if (seg.path !== pathRef.current) {
      segmentChanged = true;
      const nextSlot: PlaybackMediaSlot = {
        url: playbackApi.mediaUrl(seg.path),
        startTs: seg.start_ts,
        endTs: seg.end_ts,
      };
      pathRef.current = seg.path;
      slotRef.current = nextSlot;
      setSlot(nextSlot);
    }

    if (preload) {
      if (nxt) {
        const nextUrl = playbackApi.mediaUrl(nxt.path);
        if (preload.getAttribute('src') !== nextUrl) {
          preload.setAttribute('src', nextUrl);
          preload.preload = 'auto';
          try {
            preload.load();
          } catch {
            /* ignore */
          }
        }
      } else if (preload.getAttribute('src')) {
        preload.removeAttribute('src');
      }
    }

    if (segmentChanged) return;

    const v = ref.current;
    const current = slotRef.current;
    if (!v || !current) return;

    if (playing && !scrubbingRef.current) {
      if (v.seeking) return;
      const videoGlobal = current.startTs + v.currentTime;
      if (Math.abs(position - videoGlobal) > 0.35) {
        seekPlaybackVideo(v, position, current.startTs, { playing: true, thresholdSec: 0.35 });
        return;
      }
      if (!clockId || shouldEmitPlaybackClock(clockId, v)) {
        onVideoClockRef.current?.(videoGlobal);
      }
      return;
    }

    seekPlaybackVideo(v, position, current.startTs, {
      playing,
      scrubbing: scrubbingRef.current,
    });
  };

  useEffect(() => {
    const onTimeUpdate = () => {
      if (scrubbingRef.current) {
        applySync();
        return;
      }
      if (playing) {
        const v = ref.current;
        const current = slotRef.current;
        if (v?.seeking) return;
        if (v && current && (!clockId || shouldEmitPlaybackClock(clockId, v))) {
          onVideoClockRef.current?.(current.startTs + v.currentTime);
        }
      }
    };
    const onReady = () => applySync();
    const v = ref.current;
    if (!v) return;
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('loadeddata', onReady);
    v.addEventListener('seeked', onReady);
    applySync();

    return () => {
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('loadeddata', onReady);
      v.removeEventListener('seeked', onReady);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, segments, slot?.url, playMode, scrubbing]);

  useEffect(() => {
    applySync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec, playMode, scrubbing]);

  return { ref, preloadRef, slot, applySync };
}

export function usePlaybackCameraMetadata({
  cameraId,
  camera,
  positionSec,
  runId,
  showMetadata,
  hasVideo,
  frameSize,
  playing = false,
  detectionItems = [],
  globalDetectionTs = [],
  detectionsReady = true,
}: {
  cameraId: string;
  camera?: PlaybackCamera;
  positionSec: number;
  runId: number | null;
  showMetadata: boolean;
  hasVideo: boolean;
  frameSize?: FrameSize | null;
  playing?: boolean;
  detectionItems?: PlaybackDetectionItem[];
  globalDetectionTs?: number[];
  detectionsReady?: boolean;
}) {
  const atCameraDetection = useMemo(
    () =>
      hasActiveTrackAt(detectionItems, positionSec) ||
      objectsFromDetectionIndex(detectionItems, positionSec).length > 0,
    [detectionItems, positionSec],
  );
  const showObjects = shouldShowPlaybackObjects({
    showMetadata,
    globalTsLength: globalDetectionTs.length,
    atCameraDetection,
    detectionsReady,
  });
  const optimisticObjects = useMemo(
    () => objectsToOverlayFromIndex(detectionItems, positionSec, frameSize),
    [detectionItems, positionSec, frameSize],
  );

  const staticMeta = usePlaybackStaticMetadata({
    camera: cameraId,
    sourceId: camera?.source_id,
    runId,
    enabled: showMetadata,
    frameSize,
  });
  const { meta: dynamicMeta, loading } = usePlaybackMetadata({
    camera: cameraId,
    sourceId: camera?.source_id,
    positionSec,
    runId,
    enabled: showMetadata && hasVideo && showObjects,
    frameSize,
    playing,
    hasDetectionAtPosition: showObjects,
  });

  const meta = useMemo(() => {
    const merged = mergePlaybackMetadata(staticMeta, dynamicMeta);
    if (!showMetadata || !merged) return merged;
    if (!showObjects) return { ...merged, objects: [] };
    const metaTs = dynamicMeta?.ts;
    const fresh = metaTs != null && Math.abs(metaTs - positionSec) < 0.3;
    if (fresh) return merged;
    if (optimisticObjects.length) {
      return {
        ...merged,
        objects: optimisticObjects,
        overlay: {
          ...merged.overlay,
          time_label: overlayTimeLabel(positionSec),
        },
      };
    }
    return merged;
  }, [staticMeta, dynamicMeta, showMetadata, showObjects, optimisticObjects, positionSec]);

  return { meta, loading, showObjects };
}

export function PlaybackVideoSurface({
  videoRef,
  preloadRef,
  slot,
  mediaRef,
  meta,
  showMetadata,
  videoReady,
  setVideoReady,
  cameraLabel,
  expanded = false,
  onExpand,
  onVideoReady,
  onVideoDimensions,
  playing,
  speed,
  playMode = 'normal',
  loading = false,
  segmentsLoading = false,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  preloadRef: RefObject<HTMLVideoElement | null>;
  slot: PlaybackMediaSlot | null;
  mediaRef: RefObject<HTMLDivElement | null>;
  meta: StreamMetadata | null;
  showMetadata: boolean;
  videoReady: number;
  setVideoReady: (fn: (n: number) => number) => void;
  cameraLabel: string;
  expanded?: boolean;
  onExpand?: () => void;
  onVideoReady?: () => void;
  onVideoDimensions?: (size: FrameSize) => void;
  playing: boolean;
  speed: number;
  playMode?: PlaybackPlayMode;
  loading?: boolean;
  segmentsLoading?: boolean;
}) {
  const { t } = useI18n();
  const [seeking, setSeeking] = useState(false);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onSeeking = () => setSeeking(true);
    const onSeeked = () => setSeeking(false);
    v.addEventListener('seeking', onSeeking);
    v.addEventListener('seeked', onSeeked);
    setSeeking(v.seeking);
    return () => {
      v.removeEventListener('seeking', onSeeking);
      v.removeEventListener('seeked', onSeeked);
    };
  }, [videoRef, slot?.url]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = speed;
    if (playing) void v.play().catch(() => null);
    else v.pause();
  }, [playing, speed, slot?.url, videoRef]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  return (
    <>
      {slot?.url ? (
        <>
          <video
            ref={videoRef as RefObject<HTMLVideoElement>}
            src={slot.url}
            playsInline
            preload="auto"
            className={previewClass}
            onLoadedMetadata={() => {
              const v = videoRef.current;
              if (v?.videoWidth && v.videoHeight) {
                onVideoDimensions?.({ w: v.videoWidth, h: v.videoHeight });
              }
              setVideoReady((n) => n + 1);
              onVideoReady?.();
            }}
            onSeeked={() => onVideoReady?.()}
            onDoubleClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onExpand?.();
            }}
          />
          <video ref={preloadRef as RefObject<HTMLVideoElement>} muted playsInline style={{ display: 'none' }} aria-hidden />
          <PlaybackMediaWithOverlay
            videoRef={videoRef}
            mediaRef={mediaRef}
            meta={meta}
            showMetadata={showMetadata}
            videoReady={videoReady}
            density={expanded ? 'full' : 'compact'}
          />
          <PlaybackBusyHint
            seeking={seeking}
            loading={loading}
            hasObjects={(meta?.objects?.length ?? 0) > 0}
          />
        </>
      ) : (
        <div className={`${previewClass} camera-preview-empty`}>
          {segmentsLoading ? t('playback.loadingSegment') : t('playback.noSegment')}
        </div>
      )}
      <div className="camera-card-overlay-top">
        <span className="camera-name">{cameraLabel}</span>
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
    </>
  );
}
