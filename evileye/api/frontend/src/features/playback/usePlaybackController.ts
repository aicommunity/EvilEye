import { useCallback, useEffect, useRef, useState } from 'react';
import { detectionTsAtOrNull, nextDetectionTs, shouldSkipToDetection } from './detectionSync';

const UI_THROTTLE_MS = 100;

export function usePlaybackController(initialSec: number | null) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fromSec, setFromSec] = useState<number | null>(null);
  const [toSec, setToSec] = useState<number | null>(null);
  const [positionSec, setPositionSec] = useState<number>(initialSec ?? 0);
  const positionRef = useRef<number>(initialSec ?? 0);
  const raf = useRef<number | null>(null);
  const last = useRef<number>(0);
  const lastUi = useRef<number>(0);
  const detectionTsRef = useRef<number[]>([]);
  const skipEnabledRef = useRef(false);
  const scrubbingRef = useRef(false);

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
    positionRef.current = sec;
    if (Date.now() - lastUi.current >= UI_THROTTLE_MS) {
      lastUi.current = Date.now();
      setPositionSec(sec);
    }
  }, []);

  useEffect(() => {
    if (!playing) {
      if (raf.current) cancelAnimationFrame(raf.current);
      setPositionSec(positionRef.current);
      return;
    }
    last.current = performance.now();
    lastUi.current = last.current;
    const tick = (now: number) => {
      const dt = ((now - last.current) / 1000) * speed;
      last.current = now;
      let next = positionRef.current + dt;
      if (!scrubbingRef.current && skipEnabledRef.current) {
        const pos = positionRef.current;
        if (detectionTsAtOrNull(detectionTsRef.current, pos) == null) {
          const nextDet = nextDetectionTs(detectionTsRef.current, pos);
          if (shouldSkipToDetection(pos, nextDet)) {
            next = nextDet as number;
          }
        }
      }
      if (toSec != null && next > toSec) {
        next = toSec;
        positionRef.current = next;
        setPlaying(false);
        setPositionSec(next);
        return;
      }
      positionRef.current = next;
      if (now - lastUi.current >= UI_THROTTLE_MS) {
        lastUi.current = now;
        setPositionSec(next);
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [playing, speed, toSec]);

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
      positionRef.current = sec;
      setPositionSec(sec);
    },
    setDetectionTimestamps,
    setSkipEnabled,
    setScrubbing,
    syncPositionFromVideo,
  };
}
