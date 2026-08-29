import { useCallback, useMemo, useState } from 'react';
import {
  DAY_LOAD_BUFFER_SEC,
  MAX_VIEW_SPAN_SEC,
  MIN_VIEW_SPAN_SEC,
  clampView,
  dayBoundsLocal,
  dayViewSpanSec,
  dayViewUpperBound,
  defaultTimelineView,
  intervalsExtent,
  mergeLoadedIntervals,
  panView,
  uncoveredIntervals,
  zoomViewAt,
  zoomViewWithinDay,
  type TimeInterval,
} from './timelineMath';

const LOAD_COVERAGE_MARGIN_SEC = 600;

export function useTimelineViewport() {
  const [viewFrom, setViewFrom] = useState<number | null>(null);
  const [viewTo, setViewTo] = useState<number | null>(null);
  const [loadedIntervals, setLoadedIntervals] = useState<TimeInterval[]>([]);

  const extent = useMemo(() => intervalsExtent(loadedIntervals), [loadedIntervals]);
  const loadedFrom = extent?.from ?? null;
  const loadedTo = extent?.to ?? null;

  const setView = useCallback((from: number, to: number, dateStr?: string) => {
    const maxSpan = dateStr ? dayViewSpanSec(dateStr) : MAX_VIEW_SPAN_SEC;
    const next = clampView(from, to, { minSpan: MIN_VIEW_SPAN_SEC, maxSpan });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  const resetToData = useCallback((dataFrom: number | null, dataTo: number | null, date: string) => {
    // Honest loaded range: unknown until segments return (do not fake full-day loaded).
    if (dataFrom != null && dataTo != null && dataTo > dataFrom) {
      setLoadedIntervals([{ from: dataFrom, to: dataTo }]);
    } else {
      setLoadedIntervals([]);
    }
    const next = defaultTimelineView(date, { dataFrom, dataTo });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  /** Add request coverage without filling gaps between disjoint windows. */
  const expandLoaded = useCallback((from: number, to: number) => {
    if (!(to > from)) return;
    setLoadedIntervals((prev) => mergeLoadedIntervals(prev, { from, to }));
  }, []);

  /** Replace loaded coverage (hard-load); do not expand past a fresh request window. */
  const setLoadedRange = useCallback((from: number, to: number) => {
    if (!(to > from)) {
      setLoadedIntervals([]);
      return;
    }
    setLoadedIntervals([{ from, to }]);
  }, []);

  const needsLoad = useCallback(
    (vf: number, vt: number, dateStr: string) => {
      const { start } = dayBoundsLocal(dateStr);
      const upper = dayViewUpperBound(dateStr);
      const needFrom = Math.max(start, vf - DAY_LOAD_BUFFER_SEC);
      const needTo = Math.min(upper, vt + DAY_LOAD_BUFFER_SEC);
      const gaps = uncoveredIntervals(
        { from: needFrom, to: needTo },
        loadedIntervals,
        { marginSec: LOAD_COVERAGE_MARGIN_SEC },
      );
      if (!gaps.length) {
        return { needFrom, needTo, needed: false, gaps: [] as TimeInterval[] };
      }
      return {
        needFrom: Math.min(...gaps.map((g) => g.from)),
        needTo: Math.max(...gaps.map((g) => g.to)),
        needed: true,
        gaps,
      };
    },
    [loadedIntervals],
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
    loadedIntervals,
    setView,
    resetToData,
    expandLoaded,
    setLoadedRange,
    needsLoad,
    zoomAt,
    panBySec,
  };
}
