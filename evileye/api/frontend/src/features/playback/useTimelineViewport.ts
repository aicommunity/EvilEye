import { useCallback, useState } from 'react';
import {
  DAY_LOAD_BUFFER_SEC,
  MAX_VIEW_SPAN_SEC,
  MIN_VIEW_SPAN_SEC,
  clampView,
  dayBoundsLocal,
  dayViewSpanSec,
  dayViewUpperBound,
  defaultTimelineView,
  panView,
  zoomViewAt,
  zoomViewWithinDay,
} from './timelineMath';

export function useTimelineViewport() {
  const [viewFrom, setViewFrom] = useState<number | null>(null);
  const [viewTo, setViewTo] = useState<number | null>(null);
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null);
  const [loadedTo, setLoadedTo] = useState<number | null>(null);

  const setView = useCallback((from: number, to: number, dateStr?: string) => {
    const maxSpan = dateStr ? dayViewSpanSec(dateStr) : MAX_VIEW_SPAN_SEC;
    const next = clampView(from, to, { minSpan: MIN_VIEW_SPAN_SEC, maxSpan });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  const resetToData = useCallback((dataFrom: number | null, dataTo: number | null, date: string) => {
    // Honest loaded range: unknown until segments return (do not fake full-day loaded).
    if (dataFrom != null && dataTo != null && dataTo > dataFrom) {
      setLoadedFrom(dataFrom);
      setLoadedTo(dataTo);
    } else {
      setLoadedFrom(null);
      setLoadedTo(null);
    }
    const next = defaultTimelineView(date, { dataFrom, dataTo });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  const expandLoaded = useCallback((from: number, to: number) => {
    setLoadedFrom((prev) => (prev == null ? from : Math.min(prev, from)));
    setLoadedTo((prev) => (prev == null ? to : Math.max(prev, to)));
  }, []);

  /** Replace loaded coverage (hard-load); do not expand past a fresh request window. */
  const setLoadedRange = useCallback((from: number, to: number) => {
    setLoadedFrom(from);
    setLoadedTo(to);
  }, []);

  const needsLoad = useCallback(
    (vf: number, vt: number, dateStr: string) => {
      const { start } = dayBoundsLocal(dateStr);
      const upper = dayViewUpperBound(dateStr);
      const needFrom = Math.max(start, vf - DAY_LOAD_BUFFER_SEC);
      const needTo = Math.min(upper, vt + DAY_LOAD_BUFFER_SEC);
      if (loadedFrom == null || loadedTo == null) return { needFrom, needTo, needed: true };
      const margin = 600;
      const needed = needFrom < loadedFrom - margin || needTo > loadedTo + margin;
      return { needFrom, needTo, needed };
    },
    [loadedFrom, loadedTo],
  );

  const zoomAt = useCallback(
    (anchorUnix: number, factor: number, dateStr?: string) => {
      if (viewFrom == null || viewTo == null) return;
      if (dateStr) {
        const next = zoomViewWithinDay(viewFrom, viewTo, anchorUnix, factor, dateStr);
        setViewFrom(next.viewFrom);
        setViewTo(next.viewTo);
        return next;
      }
      const next = zoomViewAt(viewFrom, viewTo, anchorUnix, factor, {
        maxSpan: MAX_VIEW_SPAN_SEC,
        minSpan: MIN_VIEW_SPAN_SEC,
      });
      setViewFrom(next.viewFrom);
      setViewTo(next.viewTo);
      return next;
    },
    [viewFrom, viewTo],
  );

  const panBySec = useCallback(
    (deltaSec: number) => {
      if (viewFrom == null || viewTo == null) return;
      const next = panView(viewFrom, viewTo, deltaSec, {
        dataMin: loadedFrom ?? undefined,
        dataMax: loadedTo ?? undefined,
      });
      setViewFrom(next.viewFrom);
      setViewTo(next.viewTo);
      return next;
    },
    [viewFrom, viewTo, loadedFrom, loadedTo],
  );

  return {
    viewFrom,
    viewTo,
    loadedFrom,
    loadedTo,
    setView,
    resetToData,
    expandLoaded,
    setLoadedRange,
    needsLoad,
    zoomAt,
    panBySec,
  };
}
