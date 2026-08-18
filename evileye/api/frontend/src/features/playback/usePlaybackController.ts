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
  const last = useRef<number>(0);
  const detectionTsRef = useRef<number[]>([]);
  const skipEnabledRef = useRef(false);
  const scrubbingRef = useRef(false);
  const playingRef = useRef(false);
  const toSecRef = useRef<number | null>(null);
  const seekHoldTimer = useRef<number | null>(null);

  playingRef.current = playing;
  toSecRef.current = toSec;

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
    positionRef.current = next;
    setPositionSec(next);
  }, []);

  useEffect(() => {
    if (!playing) {
      if (raf.current) cancelAnimationFrame(raf.current);
      setPositionSec(positionRef.current);
      return;
    }
    resetPlaybackClockOwner();
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [playing]);

  useEffect(() => {
    return () => {
      if (seekHoldTimer.current != null) window.clearTimeout(seekHoldTimer.current);
    };
  }, []);

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
      scrubbingRef.current = true;
      if (seekHoldTimer.current != null) window.clearTimeout(seekHoldTimer.current);
      seekHoldTimer.current = window.setTimeout(() => {
        scrubbingRef.current = false;
        seekHoldTimer.current = null;
      }, 2000);
    },
    setDetectionTimestamps,
    setSkipEnabled,
    setScrubbing,
    syncPositionFromVideo,
  };
}
