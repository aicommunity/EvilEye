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
import { playbackDebugInc } from './playbackDebug';
import { clientTelemetryLog } from '../../diagnostics/clientTelemetry';
import {
  drainVideoElement,
  noteSameSrcMediaError,
  reloadVideoMedia,
  resetErrorMediaBackoff,
  scheduleErrorMediaReload,
} from './drainVideo';
import { advanceOrStopAtEof } from './playbackEof';
import { seekPlaybackVideo, shouldEmitPlaybackClock, isPastDecodedEof, seekingAgeMs, lowReadyStateAgeMs, SEEKING_STUCK_MS, LOW_READY_RELOAD_MS, resetPlaybackClockOwner } from './playbackVideoSync';
import { usePlaybackMetadata } from './usePlaybackMetadata';
import { usePlaybackStaticMetadata } from './usePlaybackStaticMetadata';
import { PlaybackStaticFrame } from './PlaybackStaticFrame';
import type { StaticFrameSource } from './markerNavigation';
import { isPositionInRecordingSegment, pickContainingPlayableSegment, isPositionInPlayableGap } from './timelineMath';

const PLAYBACK_EVENT_ZONE_PAD_SEC = 1.5;

export type PlaybackMediaSlot = {
  url: string | null;
  startTs: number;
  endTs: number;
};

export function usePlaybackCameraSlot(
  segments: PlaybackSegment[],
  getPosition: () => number,
  positionSec: number,
  playing: boolean,
  playMode: PlaybackPlayMode = 'normal',
  scrubbing = false,
  userSeeking = false,
  onVideoClock?: (globalSec: number) => void,
  clockId?: string,
  onPlaybackExhausted?: () => void,
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
  const userSeekingRef = useRef(userSeeking);
  userSeekingRef.current = userSeeking;
  const playingRef = useRef(playing);
  playingRef.current = playing;
  const onVideoClockRef = useRef(onVideoClock);
  onVideoClockRef.current = onVideoClock;
  const onPlaybackExhaustedRef = useRef(onPlaybackExhausted);
  onPlaybackExhaustedRef.current = onPlaybackExhausted;
  const [videoGlobalSec, setVideoGlobalSec] = useState<number | null>(null);
  const [videoSeeking, setVideoSeeking] = useState(false);
  const [recordingInProgress, setRecordingInProgress] = useState(false);
  const [inPlayableGap, setInPlayableGap] = useState(false);
  /**
   * Remount only as last-resort zombie recovery (not on every glitch).
   * Seek-storms on readyState 0 must not bump this.
   */
  const [mediaEpoch, setMediaEpoch] = useState(0);
  /** One initial pin per media element; chase only after HAVE_CURRENT_DATA. */
  const pinnedThisMediaRef = useRef(false);
  /** At most one remount per segment URL — remount loops reset softReloadCount. */
  const remountedUrlRef = useRef<string | null>(null);

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
    setInPlayableGap(isPositionInPlayableGap(segs, position));
    const seg = pickContainingPlayableSegment(segs, position);
    const preload = preloadRef.current;
    let segmentChanged = false;

    if (!seg) {
      if (pathRef.current != null) {
        pathRef.current = null;
        slotRef.current = null;
        setSlot(null);
        playbackDebugInc('slotNullWipes');
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

    // Never warm a next-segment <video>: each src holds a /playback/media slot
    // for the whole Range lifetime and stacks under Live↔Playback remounts.
    if (preload?.getAttribute('src')) {
      preload.removeAttribute('src');
      try {
        preload.load();
      } catch {
        /* ignore */
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

    const allowVideoClock = playing && !userSeekingRef.current;

    // Index end_ts can overrun the real mp4 duration; seeking past EOF freezes decode.
    if (isPastDecodedEof(v, position, current.startTs)) {
      const eofGlobal = current.startTs + Math.max(0, v.duration - 0.05);
      const currentSeg =
        seg ??
        pickContainingPlayableSegment(segs, current.startTs) ??
        ({
          path: pathRef.current ?? '',
          start_ts: current.startTs,
          end_ts: current.endTs,
          duration_ms: Math.max(0, (current.endTs - current.startTs) * 1000),
        } as PlaybackSegment);
      const decision = advanceOrStopAtEof(segs, currentSeg, {
        decodedDurationSec: Number.isFinite(v.duration) ? v.duration : undefined,
      });
      if (decision.action === 'advanced' && allowVideoClock && !scrubbingRef.current) {
        onVideoClockRef.current?.(decision.next.start_ts);
        return;
      }
      // Stop pin: park at EOF visually but do not keep emitting clock / reloading.
      seekPlaybackVideo(v, eofGlobal, current.startTs, {
        playing: false,
        scrubbing: scrubbingRef.current,
        force: userSeekingRef.current,
        segmentEndTs: current.endTs,
      });
      if (allowVideoClock && !scrubbingRef.current) {
        onPlaybackExhaustedRef.current?.();
      }
      return;
    }

    // While buffering (rs < 2): do not chase the shared playhead — other cams advance
    // the clock and seek-storms keep Firefox at 0↔1. Pin once when metadata exists.
    if (
      v.readyState < 2 &&
      !userSeekingRef.current &&
      !scrubbingRef.current
    ) {
      if (v.readyState >= 1 && !pinnedThisMediaRef.current) {
        pinnedThisMediaRef.current = true;
        seekPlaybackVideo(v, position, current.startTs, {
          playing,
          force: true,
          thresholdSec: 0,
          segmentEndTs: current.endTs,
        });
      }
      if (playing && v.paused) void v.play().catch(() => null);
      return;
    }

    if (playing && !scrubbingRef.current) {
      const stuckSeeking = v.seeking && seekingAgeMs(v) >= SEEKING_STUCK_MS;
      if (v.seeking && !stuckSeeking) return;
      if (stuckSeeking) {
        playbackDebugInc('seekingStuckRecoveries');
        seekPlaybackVideo(v, position, current.startTs, {
          playing: true,
          force: true,
          thresholdSec: 0,
          segmentEndTs: current.endTs,
        });
        if (v.paused) void v.play().catch(() => null);
        return;
      }
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
        if (!userSeekingRef.current) onVideoClockRef.current?.(videoGlobal);
      }
      return;
    }

    if (scrubbingRef.current && v.seeking && !userSeekingRef.current && seekingAgeMs(v) < SEEKING_STUCK_MS) {
      return;
    }

    seekPlaybackVideo(v, position, current.startTs, {
      playing,
      scrubbing: scrubbingRef.current,
      force: userSeekingRef.current,
      segmentEndTs: current.endTs,
    });
  };

  useEffect(() => {
    const onTimeUpdate = () => {
      if (!slotRef.current) return;
      publishVideoGlobal();
      if (scrubbingRef.current) return;
      if (playingRef.current) {
        const v = ref.current;
        const current = slotRef.current;
        if (v?.seeking) return;
        if (userSeekingRef.current) return;
        if (v && current && (!clockId || shouldEmitPlaybackClock(clockId, v))) {
          onVideoClockRef.current?.(current.startTs + v.currentTime);
        }
      }
    };
    const resumeIfNeeded = () => {
      const v = ref.current;
      if (!v || !playingRef.current || scrubbingRef.current) return;
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
      const currentSeg =
        pickContainingPlayableSegment(segmentsRef.current, current.startTs) ??
        ({
          path: pathRef.current ?? '',
          start_ts: current.startTs,
          end_ts: current.endTs,
          duration_ms: Math.max(0, (current.endTs - current.startTs) * 1000),
        } as PlaybackSegment);
      const decision = advanceOrStopAtEof(segmentsRef.current, currentSeg, {
        decodedDurationSec:
          ref.current && Number.isFinite(ref.current.duration) ? ref.current.duration : undefined,
      });
      if (decision.action === 'advanced' && playingRef.current && !scrubbingRef.current) {
        onVideoClockRef.current?.(decision.next.start_ts);
        return;
      }
      seekPlaybackVideo(ref.current, current.endTs, current.startTs, {
        playing: false,
        scrubbing: scrubbingRef.current,
        segmentEndTs: current.endTs,
      });
      if (playingRef.current && !scrubbingRef.current) {
        onPlaybackExhaustedRef.current?.();
      }
    };
    const errorReloadTimers: number[] = [];
    const onError = () => {
      setVideoSeeking(false);
      playbackDebugInc('playRejects');
      const src = slotRef.current?.url ?? null;
      const code = ref.current?.error?.code ?? null;
      clientTelemetryLog(
        'video_error',
        {
          camera: clockId ?? null,
          code,
          networkState: ref.current?.networkState ?? null,
          readyState: ref.current?.readyState ?? null,
          src,
        },
        'playback',
      );
      const el = ref.current;
      if (!el || !slotRef.current) return;
      const { giveUp } = noteSameSrcMediaError(el, src, code);
      if (giveUp) {
        clientTelemetryLog(
          'video_error_give_up',
          { camera: clockId ?? null, code, src },
          'playback',
        );
        const current = slotRef.current;
        const currentSeg =
          pickContainingPlayableSegment(segmentsRef.current, current.startTs) ??
          ({
            path: pathRef.current ?? '',
            start_ts: current.startTs,
            end_ts: current.endTs,
            duration_ms: Math.max(0, (current.endTs - current.startTs) * 1000),
          } as PlaybackSegment);
        const decision = advanceOrStopAtEof(segmentsRef.current, currentSeg);
        resetErrorMediaBackoff(el);
        if (decision.action === 'advanced' && playingRef.current && !scrubbingRef.current) {
          onVideoClockRef.current?.(decision.next.start_ts);
          return;
        }
        if (playingRef.current && !scrubbingRef.current) {
          onPlaybackExhaustedRef.current?.();
        }
        return;
      }
      // 503 / aborted Range → backoff reload (not fixed 400ms) to avoid shed storms.
      const timer = scheduleErrorMediaReload(el, () => {
        if (ref.current !== el || !slotRef.current) return;
        applySync();
      });
      if (timer != null) errorReloadTimers.push(timer);
    };
    const v = ref.current;
    if (!v) return;
    const onSeeking = () => setVideoSeeking(true);
    const onCanPlayReset = () => {
      resetErrorMediaBackoff(v);
      onCanPlay();
    };
    v.addEventListener('seeking', onSeeking);
    v.addEventListener('seeked', onSeeked);
    v.addEventListener('error', onError);
    setVideoSeeking(v.seeking);
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('loadeddata', onSeeked);
    v.addEventListener('loadedmetadata', onCanPlayReset);
    v.addEventListener('canplay', onCanPlayReset);
    v.addEventListener('ended', onEnded);
    applySync();
    publishVideoGlobal();
    resumeIfNeeded();

    return () => {
      for (const t of errorReloadTimers) window.clearTimeout(t);
      v.removeEventListener('seeking', onSeeking);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('error', onError);
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('loadeddata', onSeeked);
      v.removeEventListener('loadedmetadata', onCanPlayReset);
      v.removeEventListener('canplay', onCanPlayReset);
      v.removeEventListener('ended', onEnded);
    };
    // Only rebind when the media element identity changes — NOT on scrubbing/playing
    // (those used to re-seek every settle and stack "Ищем кадр").
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot?.url, mediaEpoch]);

  // Drain the element that belonged to this effect run — never ref.current in
  // cleanup (mediaEpoch remount already retargets the ref to the new <video>).
  useEffect(() => {
    const el = ref.current;
    const preload = preloadRef.current;
    return () => {
      drainVideoElement(el);
      drainVideoElement(preload);
      resetErrorMediaBackoff(el);
    };
  }, [slot?.url, mediaEpoch]);

  useEffect(() => {
    setVideoGlobalSec(null);
    setVideoSeeking(false);
    pinnedThisMediaRef.current = false;
    resetPlaybackClockOwner();
  }, [slot?.url, mediaEpoch]);

  useEffect(() => {
    remountedUrlRef.current = null;
  }, [slot?.url]);

  useEffect(() => {
    applySync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec, playMode, scrubbing, userSeeking]);

  // Recover stuck seeking even while paused (archive scrub). Prefer force-seek /
  // load() — remount at most once per URL (remount resets this effect).
  useEffect(() => {
    if (scrubbing) return;
    const v = ref.current;
    if (!v) return;
    let stuckSeekAttempts = 0;
    let pausedZombieTicks = 0;
    let softReloadCount = 0;
    const kick = () => {
      playbackDebugInc('watchdogKick');
      applySync();
      if (playingRef.current && !scrubbingRef.current && (v.paused || v.readyState < 2)) {
        playbackDebugInc('playCalls');
        void v.play().catch(() => {
          playbackDebugInc('playRejects');
        });
      }
    };
    const softReload = () => {
      // Cap recovery: reload storms reset readyState to 0 and flash «Ищем кадр».
      if (softReloadCount >= 2) return;
      softReloadCount += 1;
      pinnedThisMediaRef.current = false;
      if (reloadVideoMedia(v)) {
        kick();
      }
      const url = slotRef.current?.url ?? '';
      if (
        softReloadCount >= 2 &&
        v.readyState < 2 &&
        url &&
        remountedUrlRef.current !== url
      ) {
        remountedUrlRef.current = url;
        clientTelemetryLog(
          'video_remount',
          { camera: clockId ?? null, src: url },
          'playback',
        );
        setMediaEpoch((n) => n + 1);
      }
    };
    if (playing) {
      kick();
      v.addEventListener('canplay', kick);
    }
    const softTimer = window.setTimeout(kick, 200);
    let pullbacks = 0;
    const watchdog = window.setInterval(() => {
      const current = slotRef.current;
      if (playingRef.current && !scrubbingRef.current && v.paused) {
        pausedZombieTicks += 1;
        playbackDebugInc('playCalls');
        void v.play().catch(() => playbackDebugInc('playRejects'));
        if (pausedZombieTicks === 2 && current && v.readyState >= 2) {
          seekPlaybackVideo(v, getPositionRef.current(), current.startTs, {
            playing: true,
            force: true,
            scrubbing: true,
            thresholdSec: 0,
            segmentEndTs: current.endTs,
          });
        }
        // Only reload when truly HAVE_NOTHING for a long time (not while buffering metadata).
        if (pausedZombieTicks >= 8 && v.readyState === 0 && lowReadyStateAgeMs(v) >= LOW_READY_RELOAD_MS) {
          softReload();
        }
        return;
      }
      pausedZombieTicks = 0;

      if (v.seeking && seekingAgeMs(v) >= SEEKING_STUCK_MS && current) {
        playbackDebugInc('seekingStuckRecoveries');
        stuckSeekAttempts += 1;
        setVideoSeeking(false);
        seekPlaybackVideo(v, getPositionRef.current(), current.startTs, {
          playing: playingRef.current,
          force: true,
          scrubbing: true,
          thresholdSec: 0,
          segmentEndTs: current.endTs,
        });
        if (stuckSeekAttempts >= 4 && v.readyState === 0) {
          softReload();
        }
        return;
      }

      // HAVE_NOTHING only — HAVE_METADATA is normal Range buffering for ~180MB segments.
      if (v.readyState === 0 && lowReadyStateAgeMs(v) >= LOW_READY_RELOAD_MS && current) {
        playbackDebugInc('seekingStuckRecoveries');
        stuckSeekAttempts += 1;
        setVideoSeeking(false);
        if (stuckSeekAttempts >= 2) {
          softReload();
        }
        return;
      }

      // Paused archive can stay black after a failed Range (readyState 0, not seeking).
      if (!playingRef.current) {
        if (v.readyState === 0 && current && lowReadyStateAgeMs(v) >= LOW_READY_RELOAD_MS) {
          stuckSeekAttempts += 1;
          if (stuckSeekAttempts >= 3) {
            stuckSeekAttempts = 0;
            softReload();
          }
        } else if (v.readyState >= 2) {
          stuckSeekAttempts = 0;
          softReloadCount = 0;
        }
        return;
      }
      if (v.readyState >= 2) {
        stuckSeekAttempts = 0;
        softReloadCount = 0;
        return;
      }
      // Buffering with metadata: wait — do not pullback/reload.
      if (v.readyState >= 1) return;
      if (!(v.currentTime > 2) || pullbacks >= 4) {
        if (pullbacks >= 4 && v.readyState === 0 && lowReadyStateAgeMs(v) >= LOW_READY_RELOAD_MS) {
          softReload();
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
      if (!playingRef.current || v.readyState !== 0) return;
      if (lowReadyStateAgeMs(v) < LOW_READY_RELOAD_MS) return;
      softReload();
    }, LOW_READY_RELOAD_MS);
    return () => {
      v.removeEventListener('canplay', kick);
      window.clearTimeout(softTimer);
      window.clearTimeout(hardTimer);
      window.clearInterval(watchdog);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrubbing, playing, slot?.url, mediaEpoch]);

  return {
    ref,
    preloadRef,
    slot,
    applySync,
    videoGlobalSec,
    videoSeeking,
    recordingInProgress,
    inPlayableGap,
    mediaEpoch,
  };
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
  mediaEpoch = 0,
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
  inPlayableGap = false,
  anyCameraPlayableAtPosition = false,
  onSeekNearestPlayable,
  staticFrame = null,
  date = '',
  detectionItems = [],
  cameraId = '',
  runId = null,
  sourceId,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  preloadRef: RefObject<HTMLVideoElement | null>;
  slot: PlaybackMediaSlot | null;
  mediaEpoch?: number;
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
  inPlayableGap?: boolean;
  anyCameraPlayableAtPosition?: boolean;
  onSeekNearestPlayable?: () => void;
  staticFrame?: StaticFrameSource | null;
  date?: string;
  detectionItems?: PlaybackDetectionItem[];
  cameraId?: string;
  runId?: number | null;
  sourceId?: number | null;
}) {
  const { t } = useI18n();
  const [seeking, setSeeking] = useState(false);
  const [mediaReadyState, setMediaReadyState] = useState<number | null>(null);
  const lastSlotUrlRef = useRef<string | null>(null);
  if (slot?.url) lastSlotUrlRef.current = slot.url;
  const videoSrc = slot?.url ?? (seeking ? lastSlotUrlRef.current : null);

  const emptyMessage = (() => {
    if (segmentsLoading) return t('playback.loadingSegment');
    if (recordingInProgress) return t('playback.recordingInProgress');
    if (inPlayableGap) {
      if (anyCameraPlayableAtPosition) return t('playback.cameraNotRecordingAtTime');
      return t('playback.betweenRecordings');
    }
    return t('playback.noSegment');
  })();

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const syncReady = () => setMediaReadyState(v.readyState);
    const onSeeking = () => {
      setSeeking(true);
      syncReady();
    };
    const onSeeked = () => {
      setSeeking(false);
      syncReady();
    };
    v.addEventListener('seeking', onSeeking);
    v.addEventListener('seeked', onSeeked);
    v.addEventListener('loadeddata', syncReady);
    v.addEventListener('canplay', syncReady);
    v.addEventListener('waiting', syncReady);
    setSeeking(v.seeking);
    setMediaReadyState(v.readyState);
    // Poll readyState for BusyHint loading label — do not fake `seeking` (that
    // stuck the UI on «Ищем кадр» during normal Range buffering).
    const clearStuck = window.setInterval(() => {
      syncReady();
      if (v.readyState >= 2 && !v.seeking) setSeeking(false);
    }, 500);
    return () => {
      window.clearInterval(clearStuck);
      v.removeEventListener('seeking', onSeeking);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('loadeddata', syncReady);
      v.removeEventListener('canplay', syncReady);
      v.removeEventListener('waiting', syncReady);
    };
  }, [videoRef, slot?.url, mediaEpoch]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = speed;
    // Pause while seek-settling so media does not drift ahead of the playhead;
    // resume play only after scrubbing clears.
    if (playing && !scrubbing) {
      playbackDebugInc('playCalls');
      void v.play().catch(() => playbackDebugInc('playRejects'));
    } else {
      if (scrubbing) playbackDebugInc('pauseFromScrub');
      v.pause();
    }
  }, [playing, scrubbing, speed, slot?.url, videoRef, mediaEpoch]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  return (
    <>
      {videoSrc ? (
        <>
          <video
            key={`playback-media-${mediaEpoch}`}
            ref={videoRef as RefObject<HTMLVideoElement>}
            src={videoSrc}
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
            loading={
              Boolean(loading) ||
              (Boolean(videoSrc) && mediaReadyState != null && mediaReadyState < 2)
            }
            hasObjects={(meta?.objects?.length ?? 0) > 0}
            mediaReadyState={mediaReadyState}
          />
        </>
      ) : staticFrame?.previewPath ? (
        <PlaybackStaticFrame
          key={`${cameraId || cameraLabel}-${staticFrame.ts}-${staticFrame.previewPath}`}
          frame={staticFrame}
          date={date}
          showMetadata={showMetadata}
          cameraLabel={cameraLabel}
          detectionItems={detectionItems}
          cameraId={cameraId || cameraLabel}
          runId={runId}
          sourceId={sourceId}
          expanded={expanded}
        />
      ) : (
        <div className={`${previewClass} camera-preview-empty`}>
          <span>{emptyMessage}</span>
          {inPlayableGap && !anyCameraPlayableAtPosition && onSeekNearestPlayable ? (
            <button type="button" className="btn btn-sm btn-outline" onClick={onSeekNearestPlayable}>
              {t('playback.seekNearestRecording')}
            </button>
          ) : null}
        </div>
      )}
      {recordingInProgress && slot?.url ? (
        <div className="playback-recording-banner">{t('playback.recordingInProgress')}</div>
      ) : null}
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
