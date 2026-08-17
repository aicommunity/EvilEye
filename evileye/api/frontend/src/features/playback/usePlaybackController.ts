import { useCallback, useEffect, useRef, useState } from 'react';
import type { PlaybackPlayMode } from '../../api';
import { DETECTION_STEP_INTERVAL_MS } from './detectionSync';

const UI_THROTTLE_MS = 200;

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
  const lastStep = useRef<number>(0);
  const playModeRef = useRef<PlaybackPlayMode>('normal');
  const detectionTsRef = useRef<number[]>([]);
  const detectionIdxRef = useRef<number>(0);
  const stepIntervalMsRef = useRef<number>(DETECTION_STEP_INTERVAL_MS);

  const syncDetectionIndex = useCallback((sec: number) => {
    const sorted = detectionTsRef.current;
    if (!sorted.length) {
      detectionIdxRef.current = 0;
      return;
    }
    let idx = 0;
    while (idx < sorted.length - 1 && sorted[idx + 1] <= sec + 1e-6) idx++;
    if (sorted[idx] > sec + 1e-6) idx = 0;
    detectionIdxRef.current = idx;
  }, []);

  const setPlayMode = useCallback((mode: PlaybackPlayMode) => {
    playModeRef.current = mode;
  }, []);

  const setDetectionTimestamps = useCallback(
    (ts: number[]) => {
      detectionTsRef.current = ts;
      syncDetectionIndex(positionRef.current);
    },
    [syncDetectionIndex],
  );

  const syncPositionFromVideo = useCallback((sec: number) => {
    if (playModeRef.current !== 'normal' || !Number.isFinite(sec)) return;
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
    lastStep.current = last.current;
    const tick = (now: number) => {
      if (playModeRef.current === 'detection-sync' && detectionTsRef.current.length) {
        const interval = stepIntervalMsRef.current / Math.max(speed, 0.01);
        if (now - lastStep.current >= interval) {
          const sorted = detectionTsRef.current;
          let idx = detectionIdxRef.current;
          while (idx < sorted.length - 1 && sorted[idx] < positionRef.current - 1e-6) idx++;
          if (idx >= sorted.length - 1 && sorted[idx] <= positionRef.current + 1e-6) {
            positionRef.current = sorted[sorted.length - 1];
            setPositionSec(positionRef.current);
            setPlaying(false);
            return;
          }
          const nextIdx = Math.min(sorted.length - 1, idx + (sorted[idx] <= positionRef.current + 1e-6 ? 1 : 0));
          if (nextIdx === idx && sorted[idx] <= positionRef.current + 1e-6) {
            setPlaying(false);
            return;
          }
          detectionIdxRef.current = nextIdx;
          positionRef.current = sorted[nextIdx];
          setPositionSec(sorted[nextIdx]);
          lastStep.current = now;
        }
      } else {
        const dt = ((now - last.current) / 1000) * speed;
        last.current = now;
        let next = positionRef.current + dt;
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
        syncDetectionIndex(from);
      } else if (initialSec != null) {
        positionRef.current = initialSec;
        setPositionSec(initialSec);
        syncDetectionIndex(initialSec);
      }
    },
    seek: (sec: number) => {
      positionRef.current = sec;
      setPositionSec(sec);
      syncDetectionIndex(sec);
    },
    setPlayMode,
    setDetectionTimestamps,
    syncDetectionIndex,
    syncPositionFromVideo,
  };
}
