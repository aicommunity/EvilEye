import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { playbackApi, type PlaybackCamera, type PlaybackSegment, type StreamMetadata } from '../../api';
import { useI18n } from '../../i18n';
import { PlaybackMediaWithOverlay } from './PlaybackMediaWithOverlay';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';
import { seekPlaybackVideo } from './playbackVideoSync';
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

  const applySync = () => {
    const position = getPositionRef.current();
    const segs = segmentsRef.current;
    const seg = pickSegmentNear(segs, position);
    const nxt = nextSegment(segs, seg);
    const preload = preloadRef.current;

    if (!seg) {
      if (pathRef.current != null) {
        pathRef.current = null;
        slotRef.current = null;
        setSlot(null);
      }
    } else if (seg.path !== pathRef.current) {
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

    const v = ref.current;
    const current = slotRef.current;
    if (v && current) {
      seekPlaybackVideo(v, position, current.startTs, { playing });
    }
  };

  useEffect(() => {
    let cancelled = false;
    let rafHandle = 0;
    let vfcHandle: number | null = null;

    const schedule = () => {
      if (cancelled) return;
      applySync();
      const el = ref.current as HTMLVideoElement & {
        requestVideoFrameCallback?: (cb: () => void) => number;
        cancelVideoFrameCallback?: (h: number) => void;
      } | null;
      if (playing && el?.requestVideoFrameCallback) {
        vfcHandle = el.requestVideoFrameCallback(() => schedule());
      } else if (playing) {
        rafHandle = window.requestAnimationFrame(() => schedule());
      }
    };

    const onTimeUpdate = () => applySync();
    const onReady = () => applySync();
    const v = ref.current;
    if (!v) return;
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('loadeddata', onReady);
    v.addEventListener('seeked', onReady);
    applySync();
    if (playing) schedule();

    return () => {
      cancelled = true;
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('loadeddata', onReady);
      v.removeEventListener('seeked', onReady);
      if (vfcHandle != null && 'cancelVideoFrameCallback' in v) {
        try {
          (v as HTMLVideoElement & { cancelVideoFrameCallback: (h: number) => void }).cancelVideoFrameCallback(vfcHandle);
        } catch {
          /* ignore */
        }
      }
      if (rafHandle) window.cancelAnimationFrame(rafHandle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, segments, slot?.url]);

  useEffect(() => {
    applySync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec]);

  return { ref, preloadRef, slot, applySync };
}

export function usePlaybackCameraMetadata({
  cameraId,
  camera,
  positionSec,
  runId,
  showMetadata,
  hasVideo,
}: {
  cameraId: string;
  camera?: PlaybackCamera;
  positionSec: number;
  runId: number | null;
  showMetadata: boolean;
  hasVideo: boolean;
}): StreamMetadata | null {
  const staticMeta = usePlaybackStaticMetadata({
    camera: cameraId,
    sourceId: camera?.source_id,
    runId,
    enabled: showMetadata,
  });
  const { meta: dynamicMeta } = usePlaybackMetadata({
    camera: cameraId,
    sourceId: camera?.source_id,
    positionSec,
    runId,
    enabled: showMetadata && hasVideo,
  });
  return useMemo(() => mergePlaybackMetadata(staticMeta, dynamicMeta), [staticMeta, dynamicMeta]);
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
  playing,
  speed,
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
  playing: boolean;
  speed: number;
}) {
  const { t } = useI18n();

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
            onLoadedMetadata={() => setVideoReady((n) => n + 1)}
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
        </>
      ) : (
        <div className={`${previewClass} camera-preview-empty`}>{t('playback.noSegment')}</div>
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
