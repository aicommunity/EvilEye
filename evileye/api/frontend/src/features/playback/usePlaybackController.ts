import { useEffect, useRef, useState } from 'react';

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
    setRange: (from: number | null, to: number | null) => {
      setFromSec(from);
      setToSec(to);
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
  };
}
