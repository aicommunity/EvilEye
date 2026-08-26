import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import {
  playbackApi,
  type FrameSize,
  type PlaybackCamera,
  type PlaybackDetectionItem,
  type PlaybackEventInterval,
  type PlaybackPlayMode,
  type PlaybackSegment,
  type StreamMetadata,
} from '../../api';
import { useI18n } from '../../i18n';
import {
  overlayTimeLabel,
  resolvePlaybackOverlaySec,
  shouldShowPlaybackObjects,
} from './detectionSync';
import { PlaybackBusyHint } from './PlaybackBusyHint';
import { PlaybackMediaWithOverlay } from './PlaybackMediaWithOverlay';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';
import { seekPlaybackVideo, shouldEmitPlaybackClock, isPastDecodedEof } from './playbackVideoSync';
import { usePlaybackMetadata } from './usePlaybackMetadata';
import { usePlaybackStaticMetadata } from './usePlaybackStaticMetadata';
import { isPositionInRecordingSegment, pickPlayableSegmentForPosition, isPlayableSegment } from './timelineMath';

const PLAYBACK_EVENT_ZONE_PAD_SEC = 1.5;

export type PlaybackMediaSlot = {
  url: string | null;
  startTs: number;
  endTs: number;
};

function nextSegment(segs: PlaybackSegment[], current: PlaybackSegment | null): PlaybackSegment | null {
  if (!current || !segs.length) return null;
  const idx = segs.findIndex((s) => s.path === current.path);
  if (idx < 0) return null;
  for (let i = idx + 1; i < segs.length; i++) {
    if (isPlayableSegment(segs[i])) return segs[i];
  }
  return null;
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
  const lastAppliedPositionRef = useRef<number | null>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;
  const segmentsRef = useRef(segments);
  segmentsRef.current = segments;
  const scrubbingRef = useRef(scrubbing);
  scrubbingRef.current = scrubbing;
  const onVideoClockRef = useRef(onVideoClock);
  onVideoClockRef.current = onVideoClock;
  const [videoGlobalSec, setVideoGlobalSec] = useState<number | null>(null);
  const [videoSeeking, setVideoSeeking] = useState(false);
  const [recordingInProgress, setRecordingInProgress] = useState(false);

  const publishVideoGlobal = () => {
    const v = ref.current;
    const current = slotRef.current;
    if (!v || !current) return;
    if (v.readyState < 2) {
      // Let overlay/playhead fall back to controller clock while decode is stuck
      // (common after seek into an index overrun past real mp4 EOF).
      if (!scrubbingRef.current) setVideoGlobalSec(null);
      return;
    }
    setVideoGlobalSec(current.startTs + v.currentTime);
  };

  const applySync = () => {
    const position = getPositionRef.current();
    lastAppliedPositionRef.current = position;
    const segs = segmentsRef.current;
    setRecordingInProgress(isPositionInRecordingSegment(segs, position));
    const seg = pickPlayableSegmentForPosition(segs, position);
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

    if (segmentChanged) {
      // New src lands on next paint; pin once React commits the URL.
      requestAnimationFrame(() => {
        applySync();
      });
      return;
    }

    const v = ref.current;
    const current = slotRef.current;
    if (!v || !current) return;

    // Index end_ts can overrun the real mp4 duration; seeking past EOF freezes decode.
    if (isPastDecodedEof(v, position, current.startTs)) {
      const eofGlobal = current.startTs + Math.max(0, v.duration - 0.05);
      const nxt = nextSegment(segs, seg);
      const gapToNext = nxt ? nxt.start_ts - (current.startTs + v.duration) : Infinity;
      // Only auto-advance when the next file is contiguous; otherwise pin to real EOF
      // so a seek into the phantom index tail does not jump across a long gap.
      if (nxt && gapToNext < 2 && playing && !scrubbingRef.current) {
        onVideoClockRef.current?.(nxt.start_ts);
        return;
      }
      seekPlaybackVideo(v, eofGlobal, current.startTs, {
        playing,
        scrubbing: scrubbingRef.current,
        segmentEndTs: current.endTs,
      });
      if (Math.abs(position - eofGlobal) > 0.2) {
        onVideoClockRef.current?.(eofGlobal);
      }
      return;
    }

    if (playing && !scrubbingRef.current) {
      if (v.seeking) return;
      const videoGlobal = current.startTs + v.currentTime;
      if (Math.abs(position - videoGlobal) > 1.0) {
        seekPlaybackVideo(v, position, current.startTs, {
          playing: true,
          thresholdSec: 1.0,
          segmentEndTs: current.endTs,
        });
        // Seek-storm / src change can leave the element paused while UI still plays.
        if (v.paused) void v.play().catch(() => null);
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
      segmentEndTs: current.endTs,
    });
  };

  useEffect(() => {
    const onTimeUpdate = () => {
      publishVideoGlobal();
      // While scrubbing/seek-settling, pin from position/loadeddata — not every
      // timeupdate (that fought playback and left elements paused).
      if (scrubbingRef.current) return;
      if (playing) {
        const v = ref.current;
        const current = slotRef.current;
        if (v?.seeking) return;
        if (v && current && (!clockId || shouldEmitPlaybackClock(clockId, v))) {
          onVideoClockRef.current?.(current.startTs + v.currentTime);
        }
      }
    };
    const resumeIfNeeded = () => {
      const v = ref.current;
      if (!v || !playing || scrubbingRef.current) return;
      if (v.paused || v.readyState < 2) {
        void v.play().catch(() => null);
      }
    };
    const onSeeked = () => {
      setVideoSeeking(false);
      publishVideoGlobal();
      // Always pin after browser seek/load — including during scrubbing after a
      // segment URL change (otherwise new src stays at t=0 until settle ends).
      applySync();
      resumeIfNeeded();
    };
    const onCanPlay = () => {
      publishVideoGlobal();
      applySync();
      resumeIfNeeded();
    };
    const onEnded = () => {
      const current = slotRef.current;
      if (!current) return;
      const nxt = nextSegment(segmentsRef.current, pickPlayableSegmentForPosition(segmentsRef.current, current.startTs));
      if (nxt && playing && !scrubbingRef.current) {
        onVideoClockRef.current?.(nxt.start_ts);
        return;
      }
      seekPlaybackVideo(ref.current, current.endTs, current.startTs, {
        playing: false,
        scrubbing: scrubbingRef.current,
        segmentEndTs: current.endTs,
      });
    };
    const v = ref.current;
    if (!v) return;
    const onSeeking = () => setVideoSeeking(true);
    v.addEventListener('seeking', onSeeking);
    v.addEventListener('seeked', onSeeked);
    setVideoSeeking(v.seeking);
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('loadeddata', onSeeked);
    v.addEventListener('loadedmetadata', onCanPlay);
    v.addEventListener('canplay', onCanPlay);
    v.addEventListener('ended', onEnded);
    applySync();
    publishVideoGlobal();
    resumeIfNeeded();

    return () => {
      v.removeEventListener('seeking', onSeeking);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('loadeddata', onSeeked);
      v.removeEventListener('loadedmetadata', onCanPlay);
      v.removeEventListener('canplay', onCanPlay);
      v.removeEventListener('ended', onEnded);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, segments, slot?.url, playMode, scrubbing]);

  useEffect(() => {
    setVideoGlobalSec(null);
    setVideoSeeking(false);
  }, [slot?.url]);

  useEffect(() => {
    applySync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec, playMode, scrubbing]);

  // After seek-settle, pin + resume. Avoid immediate load() (aborts in-flight
  // decode); only reload if still HAVE_NOTHING after a short grace.
  // Some mp4s report a longer duration than decodable media — pull back if stuck.
  useEffect(() => {
    if (scrubbing || !playing) return;
    const v = ref.current;
    if (!v) return;
    const kick = () => {
      applySync();
      if (v.paused || v.readyState < 2) void v.play().catch(() => null);
    };
    kick();
    v.addEventListener('canplay', kick);
    const softTimer = window.setTimeout(kick, 200);
    let pullbacks = 0;
    const watchdog = window.setInterval(() => {
      if (v.readyState >= 2) return;
      if (!(v.currentTime > 2) || pullbacks >= 4) {
        if (pullbacks >= 4 && v.readyState < 2) {
          try {
            v.load();
          } catch {
            /* ignore */
          }
          kick();
        }
        return;
      }
      pullbacks += 1;
      try {
        v.currentTime = Math.max(0, v.currentTime - 3);
      } catch {
        /* ignore */
      }
      void v.play().catch(() => null);
    }, 700);
    const hardTimer = window.setTimeout(() => {
      if (v.readyState >= 2) return;
      try {
        v.load();
      } catch {
        /* ignore */
      }
      kick();
    }, 2800);
    return () => {
      v.removeEventListener('canplay', kick);
      window.clearTimeout(softTimer);
      window.clearTimeout(hardTimer);
      window.clearInterval(watchdog);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrubbing, playing, slot?.url]);

  return { ref, preloadRef, slot, applySync, videoGlobalSec, videoSeeking, recordingInProgress };
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
  scrubbing = false,
  videoGlobalSec = null,
  videoSeeking = false,
  detectionItems = [],
  globalDetectionTs = [],
  eventIntervals = [],
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
  scrubbing?: boolean;
  videoGlobalSec?: number | null;
  videoSeeking?: boolean;
  detectionItems?: PlaybackDetectionItem[];
  globalDetectionTs?: number[];
  eventIntervals?: PlaybackEventInterval[];
  detectionsReady?: boolean;
}) {
  const overlaySec = useMemo(
    () =>
      resolvePlaybackOverlaySec(positionSec, videoGlobalSec, {
        playing,
        videoSeeking,
        scrubbing,
      }),
    [positionSec, videoGlobalSec, playing, videoSeeking, scrubbing],
  );
  const showObjects = shouldShowPlaybackObjects({
    showMetadata,
    atCameraDetection: false,
    detectionsReady,
  });

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
    positionSec: overlaySec,
    runId,
    enabled: showMetadata && hasVideo && showObjects,
    frameSize,
    playing,
    hasDetectionAtPosition: showObjects,
  });

  const activeEvent = useMemo(() => {
    const active = eventIntervals.filter((it) => overlaySec >= it.start_ts && overlaySec <= it.end_ts);
    if (!active.length) return null;
    active.sort((a, b) => {
      if (a.start_ts !== b.start_ts) return b.start_ts - a.start_ts;
      return String(b.severity ?? '').localeCompare(String(a.severity ?? ''));
    });
    return active[0];
  }, [eventIntervals, overlaySec]);
  const activeEventLabel = useMemo(() => {
    if (!activeEvent) return null;
    const base = activeEvent.label ?? activeEvent.event_type;
    const range = `${overlayTimeLabel(activeEvent.start_ts)}-${overlayTimeLabel(activeEvent.end_ts)}`;
    const zone = activeEvent.zone_name ? ` (${activeEvent.zone_name})` : '';
    return `${base} ${range}${zone}`;
  }, [activeEvent]);
  const highlightedZoneName = useMemo(() => {
    const withPad = eventIntervals.filter(
      (it) =>
        it.zone_name &&
        overlaySec >= it.start_ts - PLAYBACK_EVENT_ZONE_PAD_SEC &&
        overlaySec <= it.end_ts + PLAYBACK_EVENT_ZONE_PAD_SEC,
    );
    if (!withPad.length) return null;
    withPad.sort((a, b) => b.start_ts - a.start_ts);
    return withPad[0].zone_name ?? null;
  }, [eventIntervals, overlaySec]);

  const meta = useMemo(() => {
    // Archive: never inject detection object bboxes — only zones/ROI/events/labels.
    const merged = mergePlaybackMetadata(staticMeta, dynamicMeta, { stripObjects: true });
    if (!showMetadata || !merged) return merged;
    const staticOnly = mergePlaybackMetadata(staticMeta, null, { stripObjects: true }) ?? merged;
    return {
      ...staticOnly,
      objects: [],
      signalization: Boolean(activeEvent),
      event_labels: activeEventLabel ? [activeEventLabel] : [],
      highlight_zone_name: highlightedZoneName,
      overlay: {
        ...staticOnly.overlay,
        source_name: staticOnly.overlay?.source_name || cameraId,
        time_label: overlayTimeLabel(overlaySec),
      },
    };
  }, [staticMeta, dynamicMeta, showMetadata, overlaySec, activeEvent, activeEventLabel, highlightedZoneName, cameraId]);

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
  scrubbing = false,
  speed,
  playMode = 'normal',
  loading = false,
  segmentsLoading = false,
  recordingInProgress = false,
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
  scrubbing?: boolean;
  speed: number;
  playMode?: PlaybackPlayMode;
  loading?: boolean;
  segmentsLoading?: boolean;
  recordingInProgress?: boolean;
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
    // Pause while seek-settling so media does not drift ahead of the playhead;
    // resume play only after scrubbing clears.
    if (playing && !scrubbing) void v.play().catch(() => null);
    else v.pause();
  }, [playing, scrubbing, speed, slot?.url, videoRef]);

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
            visible={showMetadata}
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
          {segmentsLoading
            ? t('playback.loadingSegment')
            : recordingInProgress
              ? t('playback.recordingInProgress')
              : t('playback.noSegment')}
        </div>
      )}
      {recordingInProgress && slot?.url ? (
        <div className="playback-recording-banner">{t('playback.recordingInProgress')}</div>
      ) : null}
      {!showMetadata ? <div className="live-overlay-source">{cameraLabel}</div> : null}
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
