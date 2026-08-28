import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react';
import {
  dayBoundsLocal,
  dayViewSpanSec,
  dayViewUpperBound,
  localDateString,
} from './timelineMath';
import {
  playbackDebugMarkSettleEnter,
  playbackDebugMarkSettleExit,
} from './playbackDebug';
import {
  createUserSeekGuard,
  resolveUserSeekTarget,
  SEEK_SETTLE_HOLD_MS,
  type UserSeekGuard,
} from './playbackSeek';
import type { usePlaybackController } from './usePlaybackController';
import type { useTimelineViewport } from './useTimelineViewport';

const INITIAL_WINDOW_SEC = 7200;
const SEEK_LOAD_HALF_SEC = 3600;

type Ctrl = ReturnType<typeof usePlaybackController>;
type Viewport = ReturnType<typeof useTimelineViewport>;

export function usePlaybackSeek(opts: {
  ctrl: Ctrl;
  viewport: Viewport;
  date: string;
  setDate: (d: string) => void;
  dateChangeSourceRef: MutableRefObject<'user' | 'viewport' | 'seek'>;
  pendingViewportLoadRef: MutableRefObject<{ date: string; from: number; to: number } | null>;
  loadTimerRef: MutableRefObject<number | null>;
  ensureAdjacentLoad: (from: number, to: number) => void;
  userSeekGuardRef: MutableRefObject<UserSeekGuard>;
}) {
  const {
    ctrl,
    viewport,
    date,
    setDate,
    dateChangeSourceRef,
    pendingViewportLoadRef,
    loadTimerRef,
    ensureAdjacentLoad,
    userSeekGuardRef,
  } = opts;

  const seekSettleTimerRef = useRef<number | null>(null);
  const [holdVideoClock, setHoldVideoClock] = useState(false);
  const [userSeeking, setUserSeeking] = useState(false);

  const seek = useCallback(
    (sec: number) => {
      const target = resolveUserSeekTarget(sec);
      const nextDate = localDateString(target);
      if (nextDate !== date) {
        dateChangeSourceRef.current = 'seek';
        const { start } = dayBoundsLocal(nextDate);
        const upper = dayViewUpperBound(nextDate);
        pendingViewportLoadRef.current = {
          date: nextDate,
          from: Math.max(start, target - SEEK_LOAD_HALF_SEC),
          to: Math.min(upper, target + SEEK_LOAD_HALF_SEC),
        };
        setDate(nextDate);
        const span = Math.min(dayViewSpanSec(nextDate), INITIAL_WINDOW_SEC);
        viewport.setView(Math.max(start, target - span / 2), Math.min(upper, target + span / 2), nextDate);
      }
      userSeekGuardRef.current.markUserSeek();
      ctrl.beginUserSeek(target);
      ctrl.seek(target);
      setUserSeeking(true);
      setHoldVideoClock(true);
      ctrl.setScrubbing(true);
      playbackDebugMarkSettleEnter();
      if (seekSettleTimerRef.current != null) window.clearTimeout(seekSettleTimerRef.current);
      seekSettleTimerRef.current = window.setTimeout(() => {
        setHoldVideoClock(false);
        ctrl.setScrubbing(false);
        seekSettleTimerRef.current = null;
        playbackDebugMarkSettleExit();
        ctrl.beginClockGrace();
      }, SEEK_SETTLE_HOLD_MS);
      window.setTimeout(() => setUserSeeking(false), 2000);
      if (loadTimerRef.current) window.clearTimeout(loadTimerRef.current);
      loadTimerRef.current = window.setTimeout(() => {
        ensureAdjacentLoad(target - SEEK_LOAD_HALF_SEC, target + SEEK_LOAD_HALF_SEC);
      }, SEEK_SETTLE_HOLD_MS + 100);
    },
    [
      ctrl,
      date,
      dateChangeSourceRef,
      ensureAdjacentLoad,
      loadTimerRef,
      pendingViewportLoadRef,
      setDate,
      viewport,
    ],
  );

  const cancelSeekSettle = useCallback(() => {
    if (seekSettleTimerRef.current != null) {
      window.clearTimeout(seekSettleTimerRef.current);
      seekSettleTimerRef.current = null;
    }
    setHoldVideoClock(false);
    setUserSeeking(false);
    ctrl.setScrubbing(false);
    ctrl.endUserSeek();
  }, [ctrl]);

  useEffect(() => {
    return () => {
      if (seekSettleTimerRef.current != null) window.clearTimeout(seekSettleTimerRef.current);
    };
  }, []);

  return {
    seek,
    holdVideoClock,
    userSeeking,
    userSeekGuard: userSeekGuardRef.current,
    cancelSeekSettle,
  };
}