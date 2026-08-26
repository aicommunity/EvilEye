import { useCallback, useEffect, useRef, useState } from 'react';
import { resetPlaybackClockOwner } from './playbackVideoSync';

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

  playingRef.current = playing;
  toSecRef.current = toSec;
  speedRef.current = speed;

  const setDetectionTimestamps = useCallback((ts: number[]) => {
    detectionTsRef.current = ts;
  }, []);

  const setSkipEnabled = useCallback((enabled: boolean) => {
    skipEnabledRef.current = enabled;
  }, []);

  const setScrubbing = useCallback((value: boolean) => {
    scrubbingRef.current = value;
  }, []);

  const syncPositionFromVideo = useCallback((sec: number) => {
    if (!Number.isFinite(sec) || scrubbingRef.current) return;
    let next = sec;
    const upper = toSecRef.current;
    if (playingRef.current && upper != null && next > upper) {
      next = upper;
      setPlaying(false);
    }
    lastVideoSyncAtRef.current = performance.now();
    positionRef.current = next;
    setPositionSec(next);
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
      if (scrubbingRef.current) {
        last = now;
        return;
      }
      // Primary clock is the decoded video. If it stalls after seek (readyState 0
      // zombie), advance from wall time so applySync/play can recover.
      const videoFresh = now - lastVideoSyncAtRef.current < 1200;
      if (videoFresh) {
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
      lastVideoSyncAtRef.current = performance.now();
    },
    setDetectionTimestamps,
    setSkipEnabled,
    setScrubbing,
    syncPositionFromVideo,
  };
}
