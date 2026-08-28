import { useCallback, useEffect, useRef, useState } from 'react';
import {
  playbackDebugInc,
  playbackDebugSetMeta,
} from './playbackDebug';
import { CLOCK_GRACE_MS, resetPlaybackClockOwner } from './playbackVideoSync';

export type PlayheadMode = 'idle' | 'userSeek' | 'playing' | 'stalled';

const USER_SEEK_BLOCK_MS = 2000;

type UserSeekState = {
  targetSec: number;
  startedAt: number;
  token: number;
};

export function usePlaybackController(initialSec: number | null) {
  const [playing, setPlayingState] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fromSec, setFromSec] = useState<number | null>(null);
  const [toSec, setToSec] = useState<number | null>(null);
  const [positionSec, setPositionSec] = useState<number>(initialSec ?? 0);
  const [playheadMode, setPlayheadMode] = useState<PlayheadMode>('idle');
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
  const userSeekRef = useRef<UserSeekState | null>(null);
  const userSeekEndTimerRef = useRef<number | null>(null);

  playingRef.current = playing;
  toSecRef.current = toSec;
  speedRef.current = speed;

  const clearUserSeekTimer = useCallback(() => {
    if (userSeekEndTimerRef.current != null) {
      window.clearTimeout(userSeekEndTimerRef.current);
      userSeekEndTimerRef.current = null;
    }
  }, []);

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
    if (was && !value) {
      clockGraceUntilRef.current = performance.now() + CLOCK_GRACE_MS;
    }
  }, []);

  const endUserSeek = useCallback(() => {
    clearUserSeekTimer();
    userSeekRef.current = null;
    setPlayheadMode(playingRef.current ? 'playing' : 'idle');
  }, [clearUserSeekTimer]);

  const beginUserSeek = useCallback(
    (sec: number): number => {
      clearUserSeekTimer();
      const token = (userSeekRef.current?.token ?? 0) + 1;
      userSeekRef.current = { targetSec: sec, startedAt: performance.now(), token };
      resetPlaybackClockOwner();
      setPlayheadMode('userSeek');
      userSeekEndTimerRef.current = window.setTimeout(() => {
        userSeekEndTimerRef.current = null;
        userSeekRef.current = null;
        setPlayheadMode(playingRef.current ? 'playing' : 'idle');
      }, USER_SEEK_BLOCK_MS);
      return token;
    },
    [clearUserSeekTimer],
  );

  const isUserSeekActive = useCallback((): boolean => {
    const u = userSeekRef.current;
    if (!u) return false;
    if (performance.now() - u.startedAt > USER_SEEK_BLOCK_MS) {
      userSeekRef.current = null;
      setPlayheadMode(playingRef.current ? 'playing' : 'idle');
      return false;
    }
    return true;
  }, []);

  const getUserSeekTarget = useCallback((): number | null => {
    return userSeekRef.current?.targetSec ?? null;
  }, []);

  const setPlaying = useCallback(
    (next: boolean) => {
      setPlayingState(next);
      playingRef.current = next;
      if (userSeekRef.current) {
        setPlayheadMode('userSeek');
      } else {
        setPlayheadMode(next ? 'playing' : 'idle');
      }
    },
    [],
  );

  const syncPositionFromVideo = useCallback((sec: number) => {
    if (!Number.isFinite(sec)) return;
    if (userSeekRef.current != null) {
      playbackDebugInc('userSeekBlocksSync');
      return;
    }
    if (scrubbingRef.current) return;
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
    setPlayheadMode(playingRef.current ? 'playing' : 'idle');
    playbackDebugSetMeta({ positionSec: next, playing: playingRef.current, scrubbing: scrubbingRef.current });
  }, [setPlaying]);

  useEffect(() => {
    if (!playing) {
      if (raf.current) cancelAnimationFrame(raf.current);
      raf.current = null;
      setPositionSec(positionRef.current);
      if (!userSeekRef.current) setPlayheadMode('idle');
      return;
    }
    if (!userSeekRef.current) setPlayheadMode('playing');
    resetPlaybackClockOwner();
    lastVideoSyncAtRef.current = performance.now();
    let last = performance.now();
    const tick = (now: number) => {
      raf.current = requestAnimationFrame(tick);
      playbackDebugInc('rafTicks');
      if (scrubbingRef.current || userSeekRef.current) {
        playbackDebugInc('rafSkippedScrub');
        last = now;
        return;
      }
      const videoFresh = now - lastVideoSyncAtRef.current < 1200;
      if (videoFresh) {
        playbackDebugInc('rafSkippedFresh');
        if (playheadMode !== 'stalled') setPlayheadMode('playing');
        last = now;
        return;
      }
      setPlayheadMode('stalled');
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
  }, [playing, playheadMode, setPlaying]);

  useEffect(() => () => clearUserSeekTimer(), [clearUserSeekTimer]);

  return {
    playing,
    setPlaying,
    speed,
    setSpeed,
    fromSec,
    toSec,
    positionSec,
    playheadMode,
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
      playbackDebugInc('seekCount');
      playbackDebugSetMeta({ positionSec: sec, scrubbing: scrubbingRef.current, playing: playingRef.current });
    },
    beginUserSeek,
    endUserSeek,
    isUserSeekActive,
    getUserSeekTarget,
    beginClockGrace,
    setDetectionTimestamps,
    setSkipEnabled,
    setScrubbing,
    syncPositionFromVideo,
  };
}
