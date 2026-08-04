import { useEffect, useRef, useState } from 'react';

export function usePlaybackController(initialSec: number | null) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fromSec, setFromSec] = useState<number | null>(null);
  const [toSec, setToSec] = useState<number | null>(null);
  const [positionSec, setPositionSec] = useState<number>(initialSec ?? 0);
  const raf = useRef<number | null>(null);
  const last = useRef<number>(0);

  useEffect(() => {
    if (!playing) {
      if (raf.current) cancelAnimationFrame(raf.current);
      return;
    }
    last.current = performance.now();
    const tick = (now: number) => {
      const dt = ((now - last.current) / 1000) * speed;
      last.current = now;
      setPositionSec((p) => {
        const next = p + dt;
        if (toSec != null && next > toSec) {
          setPlaying(false);
          return toSec;
        }
        return next;
      });
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
    setRange: (from: number | null, to: number | null) => {
      setFromSec(from);
      setToSec(to);
      if (from != null && (initialSec == null || initialSec < from)) setPositionSec(from);
      else if (initialSec != null) setPositionSec(initialSec);
    },
    seek: (sec: number) => setPositionSec(sec),
  };
}
