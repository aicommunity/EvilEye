import { useCallback, useEffect, useRef, useState } from 'react';
import {
  playbackDebugInc,
  playbackDebugSetMeta,
} from './playbackDebug';
import { CLOCK_GRACE_MS, resetPlaybackClockOwner } from './playbackVideoSync';

export function usePlaybackController(initialSec: number | null) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fromSec, setFromSec] = useState<number | null>(null);
  const [toSec, setToSec] = useState<number | null>(null);
  const [positionSec, setPositionSec] = useState<number>(initialSec ?? 0);
  const positionRef = useRef<number>(initialSec ?? 0);
  const raf = useRef<number | null>(null);
  const detectionTsRef = useRef<number[]>([]);
  const skipEnabledRef = useRef(false);
  const scrubbingRef = useRef(false);
  const playingRef = useRef(false);
  const toSecRef = useRef<number | null>(null);
  const speedRef = useRef(1);
  const lastVideoSyncAtRef = useRef(0);
  const clockGraceUntilRef = useRef(0);

  playingRef.current = playing;
  toSecRef.current = toSec;
  speedRef.current = speed;

  const setDetectionTimestamps = useCallback((ts: number[]) => {
    detectionTsRef.current = ts;
  }, []);

  const setSkipEnabled = useCallback((enabled: boolean) => {
    skipEnabledRef.current = enabled;
  }, []);

  const beginClockGrace = useCallback((ms = CLOCK_GRACE_MS) => {
    clockGraceUntilRef.current = performance.now() + ms;
  }, []);

  const setScrubbing = useCallback((value: boolean) => {
    const was = scrubbingRef.current;
    scrubbingRef.current = value;
    // When settle ends, ignore stale video clock briefly so playhead does not roll back.
    if (was && !value) {
      clockGraceUntilRef.current = performance.now() + CLOCK_GRACE_MS;
    }
  }, []);

  const syncPositionFromVideo = useCallback((sec: number) => {
    if (!Number.isFinite(sec) || scrubbingRef.current) return;
    const now = performance.now();
    if (now < clockGraceUntilRef.current && Math.abs(sec - positionRef.current) > 0.75) {
      playbackDebugInc('clockGraceDrops');
      return;
    }
    let next = sec;
    const upper = toSecRef.current;
    if (playingRef.current && upper != null && next > upper) {
      next = upper;
      setPlaying(false);
    }
    lastVideoSyncAtRef.current = now;
    positionRef.current = next;
    setPositionSec(next);
    playbackDebugSetMeta({ positionSec: next, playing: playingRef.current, scrubbing: scrubbingRef.current });
  }, []);

  useEffect(() => {
    if (!playing) {
      if (raf.current) cancelAnimationFrame(raf.current);
      raf.current = null;
      setPositionSec(positionRef.current);
      return;
    }
    resetPlaybackClockOwner();
    lastVideoSyncAtRef.current = performance.now();
    let last = performance.now();
    const tick = (now: number) => {
      raf.current = requestAnimationFrame(tick);
      playbackDebugInc('rafTicks');
      if (scrubbingRef.current) {
        playbackDebugInc('rafSkippedScrub');
        last = now;
        return;
      }
      // Primary clock is the decoded video. If it stalls after seek (readyState 0
      // zombie), advance from wall time so applySync/play can recover.
      const videoFresh = now - lastVideoSyncAtRef.current < 1200;
      if (videoFresh) {
        playbackDebugInc('rafSkippedFresh');
        last = now;
        return;
      }
      const dt = ((now - last) / 1000) * speedRef.current;
      last = now;
      if (!(dt > 0) || dt > 1) return;
      let next = positionRef.current + dt;
      const upper = toSecRef.current;
      if (upper != null && next > upper) {
        next = upper;
        setPlaying(false);
      }
      positionRef.current = next;
      setPositionSec(next);
      playbackDebugInc('rafAdvanced');
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
  }, [playing]);

  return {
    playing,
    setPlaying,
    speed,
    setSpeed,
    fromSec,
    toSec,
    positionSec,
    getPosition: () => positionRef.current,
    setRange: (from: number | null, to: number | null, opts?: { preservePosition?: boolean }) => {
      setFromSec(from);
      setToSec(to);
      const preserve = opts?.preservePosition === true;
      if (preserve) {
        return;
      }
      if (from != null && (initialSec == null || initialSec < from)) {
        positionRef.current = from;
        setPositionSec(from);
      } else if (initialSec != null) {
        positionRef.current = initialSec;
        setPositionSec(initialSec);
      }
    },
    seek: (sec: number) => {
      resetPlaybackClockOwner();
      positionRef.current = sec;
      setPositionSec(sec);
      // Do NOT touch lastVideoSyncAtRef — otherwise RAF fallback never starts after seek storm.
      playbackDebugInc('seekCount');
      playbackDebugSetMeta({ positionSec: sec, scrubbing: scrubbingRef.current, playing: playingRef.current });
    },
    beginClockGrace,
    setDetectionTimestamps,
    setSkipEnabled,
    setScrubbing,
    syncPositionFromVideo,
  };
}
