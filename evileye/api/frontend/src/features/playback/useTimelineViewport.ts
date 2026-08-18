import { useCallback, useState } from 'react';
import {
  DAY_LOAD_BUFFER_SEC,
  MAX_VIEW_SPAN_SEC,
  MIN_VIEW_SPAN_SEC,
  clampView,
  dayBoundsLocal,
  dayViewUpperBound,
  defaultTimelineView,
  panView,
  zoomViewAt,
} from './timelineMath';

export function useTimelineViewport() {
  const [viewFrom, setViewFrom] = useState<number | null>(null);
  const [viewTo, setViewTo] = useState<number | null>(null);
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null);
  const [loadedTo, setLoadedTo] = useState<number | null>(null);

  const setView = useCallback((from: number, to: number) => {
    const next = clampView(from, to, { minSpan: MIN_VIEW_SPAN_SEC, maxSpan: MAX_VIEW_SPAN_SEC });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  const resetToData = useCallback((dataFrom: number | null, dataTo: number | null, date: string) => {
    const bounds = dayBoundsLocal(date);
    const upper = dayViewUpperBound(date);
    if (dataFrom != null && dataTo != null && dataTo > dataFrom) {
      setLoadedFrom(dataFrom);
      setLoadedTo(dataTo);
    } else {
      setLoadedFrom(bounds.start);
      setLoadedTo(upper);
    }
    const next = defaultTimelineView(date, { dataFrom, dataTo });
    setViewFrom(next.viewFrom);
    setViewTo(next.viewTo);
  }, []);

  const expandLoaded = useCallback((from: number, to: number) => {
    setLoadedFrom((prev) => (prev == null ? from : Math.min(prev, from)));
    setLoadedTo((prev) => (prev == null ? to : Math.max(prev, to)));
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
    (anchorUnix: number, factor: number) => {
      if (viewFrom == null || viewTo == null) return;
      const next = zoomViewAt(viewFrom, viewTo, anchorUnix, factor, {
        dataMin: loadedFrom ?? undefined,
        dataMax: loadedTo ?? undefined,
      });
      setViewFrom(next.viewFrom);
      setViewTo(next.viewTo);
      return next;
    },
    [viewFrom, viewTo, loadedFrom, loadedTo],
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
    needsLoad,
    zoomAt,
    panBySec,
  };
}
