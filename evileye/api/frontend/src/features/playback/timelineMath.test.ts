import { describe, expect, it } from 'vitest';
import {
  DEFAULT_TIMELINE_WINDOW_SEC,
  DETECTION_SNAP_MAX_SEC,
  MAX_VIEW_SPAN_SEC,
  MIN_VIEW_SPAN_SEC,
  buildTimelineDateBoundaries,
  buildTimelineDateLabels,
  clampViewToDayBounds,
  clipRangeToView,
  dayBoundsLocal,
  dayViewSpanSec,
  dayViewUpperBound,
  defaultTimelineView,
  hasAnyPlayableAtPosition,
  intersectPlayableCoverage,
  intervalsExtent,
  isPositionInPlayableGap,
  isPositionInRecordingSegment,
  isPlayableAtPosition,
  mergeLoadedIntervals,
  nextPlayableStart,
  playableUnionCoverage,
  recordingUnionCoverage,
  snapUnionPositionToPlayable,
  uncoveredIntervals,
  pickContainingSegment,
  pickContainingPlayableSegment,
  pickLastPlayableSegment,
  pickPlayableSegmentForPosition,
  pickSegmentNear,
  resolveTimelineViewChange,
  snapPositionToPlayable,
  snapTimelineSeek,
  snapUnixToDetections,
  zoomViewAt,
  zoomViewWithinDay,
  panViewWithinDay,
} from './timelineMath';
import { resolveUserSeekTarget } from './playbackSeek';

describe('snapUnixToDetections', () => {
  const viewFrom = 1000;
  const viewTo = 1000 + 1000;
  const widthPx = 500;
  const detections = [1100, 1400, 1800];

  it('snaps when the click is within both 10px and the max time window', () => {
    const near = 1100 + 1.0;
    expect(snapUnixToDetections(near, detections, viewFrom, viewTo, widthPx, 10)).toBe(1100);
  });

  it('does not snap when the click is far from every tick', () => {
    expect(snapUnixToDetections(1500, detections, viewFrom, viewTo, widthPx, 10)).toBe(1500);
  });

  it('does not snap across minutes just because the day view makes 10px huge', () => {
    const dayFrom = 0;
    const dayTo = 86400;
    const clicked = 11 * 3600 + 21;
    const nearbyTick = clicked - 60;
    expect(nearbyTick - clicked).toBeLessThan(0);
    expect(
      snapUnixToDetections(clicked, [nearbyTick], dayFrom, dayTo, 800, 10),
    ).toBe(clicked);
    expect(DETECTION_SNAP_MAX_SEC).toBeLessThan(60);
  });

  it('returns the click time when there are no detections', () => {
    expect(snapUnixToDetections(1500, [], viewFrom, viewTo, widthPx)).toBe(1500);
  });
});

describe('defaultTimelineView', () => {
  it('uses a trailing window for all-day recordings instead of the full day', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const upper = start + 86400 - 1;
    const view = defaultTimelineView(date, {
      dataFrom: start + 3600,
      dataTo: upper - 3600,
      nowSec: upper - 1800,
    });
    expect(view.viewTo - view.viewFrom).toBeLessThan(upper - start);
    expect(view.viewTo).toBeGreaterThan(view.viewFrom);
    expect(view.viewTo).toBeLessThanOrEqual(upper);
  });

  it('shows a recent window before segment data arrives', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const noon = start + 12 * 3600;
    const view = defaultTimelineView(date, { nowSec: noon });
    expect(view.viewTo).toBe(noon);
    expect(view.viewFrom).toBeGreaterThanOrEqual(start);
    expect(view.viewTo - view.viewFrom).toBeLessThanOrEqual(DEFAULT_TIMELINE_WINDOW_SEC + 1);
  });
});

describe('zoom day hard stop', () => {
  it('caps MAX_VIEW_SPAN_SEC at one day', () => {
    expect(MAX_VIEW_SPAN_SEC).toBe(24 * 3600);
  });

  it('keeps closest zoom at least 5 minutes', () => {
    expect(MIN_VIEW_SPAN_SEC).toBe(5 * 60);
  });

  it('stops zooming out once the view already spans the day', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const span = dayViewSpanSec(date, start + 12 * 3600);
    const from = start;
    const to = start + span - 1;
    const next = zoomViewAt(from, to, (from + to) / 2, 2, { maxSpan: span });
    expect(next.viewTo - next.viewFrom).toBeLessThanOrEqual(span + 1e-6);
    expect(Math.abs(next.viewFrom - from) < 1 || Math.abs(next.viewTo - next.viewFrom - span) < 2).toBe(true);
  });

  it('does not cross midnight when zooming out near the day edge', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const noon = start + 12 * 3600;
    // Narrow window near midnight; zoom-out around left edge used to push viewFrom < start
    // and switch the calendar day via resolveTimelineViewChange.
    const from = start + 60;
    const to = from + 20 * 60;
    const next = zoomViewWithinDay(from, to, from + 30, 8, date, noon);
    expect(next.viewFrom).toBeGreaterThanOrEqual(start);
    expect(next.viewTo).toBeLessThanOrEqual(dayViewUpperBound(date, noon));
    expect(next.viewTo - next.viewFrom).toBeLessThanOrEqual(dayViewSpanSec(date, noon) + 1e-6);
  });

  it('refuses to zoom in closer than MIN_VIEW_SPAN_SEC', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const from = start + 3600;
    const to = from + MIN_VIEW_SPAN_SEC;
    const next = zoomViewWithinDay(from, to, (from + to) / 2, 0.5, date, start + 12 * 3600);
    expect(next.viewTo - next.viewFrom).toBeGreaterThanOrEqual(MIN_VIEW_SPAN_SEC - 1e-6);
  });

  it('keeps pan inside the day without crossing midnight', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const noon = start + 12 * 3600;
    const from = start + 60;
    const to = from + 3600;
    const next = panViewWithinDay(from, to, -7200, date, noon);
    expect(next.viewFrom).toBeGreaterThanOrEqual(start);
    expect(next.viewTo).toBeLessThanOrEqual(dayViewUpperBound(date, noon));
    expect(next.viewTo - next.viewFrom).toBeCloseTo(to - from, 5);
  });

  it('builds date-boundary ticks at local midnights', () => {
    const date = '2026-08-18';
    const { start, end } = dayBoundsLocal(date);
    const ticks = buildTimelineDateBoundaries(start, end - 1);
    expect(ticks).toContain(start);
  });
});

describe('clampViewToDayBounds', () => {
  it('keeps pan/zoom inside the selected calendar day', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const upper = start + 86400 - 1;
    const shifted = clampViewToDayBounds(start + 20 * 3600, upper + 6 * 3600, date);
    expect(shifted.viewFrom).toBeGreaterThanOrEqual(start);
    expect(shifted.viewTo).toBeLessThanOrEqual(upper);
    expect(shifted.viewTo - shifted.viewFrom).toBeGreaterThan(0);
  });

  it('clamps today to now instead of end of day', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const noon = start + 12 * 3600;
    const shifted = clampViewToDayBounds(noon - 1800, noon + 3600, date, noon);
    expect(shifted.viewTo).toBeLessThanOrEqual(noon);
  });
});

describe('resolveTimelineViewChange', () => {
  it('switches to the previous day when panning into the past', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const span = 3600;
    const resolved = resolveTimelineViewChange(start - span / 2, start + span / 2, date, start + 12 * 3600);
    expect(resolved.date).toBe('2026-08-17');
    expect(resolved.dateChanged).toBe(true);
    expect(resolved.viewFrom).toBeGreaterThanOrEqual(dayBoundsLocal('2026-08-17').start);
  });

  it('does not move past now on today', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const noon = start + 12 * 3600;
    const span = 3600;
    const resolved = resolveTimelineViewChange(noon - span / 2, noon + span, date, noon);
    expect(resolved.date).toBe(date);
    expect(resolved.viewTo).toBeLessThanOrEqual(noon);
  });
});

describe('clipRangeToView', () => {
  it('clips segments that overhang the viewport edges', () => {
    const clipped = clipRangeToView(90, 130, 100, 200);
    expect(clipped).not.toBeNull();
    expect(clipped!.leftPct).toBe(0);
    expect(clipped!.widthPct).toBe(30);
  });

  it('returns null when there is no intersection', () => {
    expect(clipRangeToView(10, 20, 100, 200)).toBeNull();
  });
});

describe('snapTimelineSeek', () => {
  it('does not snap on a day-long view even when a tick is nearby', () => {
    const dayFrom = 0;
    const dayTo = 86400;
    const clicked = 11 * 3600 + 21;
    const nearbyTick = clicked + 1;
    expect(snapTimelineSeek(clicked, [nearbyTick], dayFrom, dayTo, 800)).toBe(clicked);
  });

  it('snaps when the view is zoomed in', () => {
    const from = 10 * 3600;
    const to = from + 30 * 60;
    const tick = from + 10 * 60;
    expect(snapTimelineSeek(tick + 0.4, [tick], from, to, 800)).toBe(tick);
  });
});

describe('segment picking', () => {
  const segs = [
    { path: 'a.mp4', start_ts: 100, end_ts: 120, duration_ms: 20_000 },
    { path: 'b.mp4', start_ts: 140, end_ts: 160, duration_ms: 20_000 },
  ];

  it('picks only the containing segment for active playback', () => {
    expect(pickContainingSegment(segs, 110)?.path).toBe('a.mp4');
    expect(pickContainingSegment(segs, 130)).toBeNull();
  });

  it('still exposes nearest-segment fallback for preload use-cases', () => {
    expect(pickSegmentNear(segs, 130)?.path).toBe('a.mp4');
    expect(pickSegmentNear(segs, 158)?.path).toBe('b.mp4');
  });

  it('skips non-playable segments for media src', () => {
    const mixed = [
      { path: 'closed.mp4', start_ts: 100, end_ts: 120, duration_ms: 20_000, playable: true },
      { path: 'open.mp4', start_ts: 120, end_ts: 140, duration_ms: 20_000, playable: false },
    ];
    expect(pickPlayableSegmentForPosition(mixed, 130)?.path).toBe('closed.mp4');
    expect(isPositionInRecordingSegment(mixed, 130)).toBe(true);
    expect(pickLastPlayableSegment(mixed)?.path).toBe('closed.mp4');
    expect(snapPositionToPlayable(mixed, 130)).toBeLessThanOrEqual(120);
  });

  it('snaps off the phantom index tail near segment end', () => {
    const long = [{ path: 'long.mp4', start_ts: 1000, end_ts: 1000 + 1818, duration_ms: 1_818_000, playable: true }];
    expect(snapPositionToPlayable(long, 1000 + 1817)).toBe(1000 + 1818 - 5);
  });
});

describe('Cam1 gap @ 18:48:29', () => {
  const cam1BeforeEnd = 1787758001;
  const cam1NextStart = 1787760687;
  const target = 1787759309;

  const cam1Segs = [
    { path: 'cam1_a.mp4', start_ts: cam1BeforeEnd - 1800, end_ts: cam1BeforeEnd, duration_ms: 1_800_000, playable: true },
    { path: 'cam1_b.mp4', start_ts: cam1NextStart, end_ts: cam1NextStart + 1800, duration_ms: 1_800_000, playable: true },
  ];
  const cam2Segs = [
    {
      path: 'cam2.mp4',
      start_ts: target - 420,
      end_ts: target + 1200,
      duration_ms: 1_620_000,
      playable: true,
    },
  ];

  it('hasAnyPlayableAtPosition is true for union', () => {
    expect(hasAnyPlayableAtPosition({ Cam1: cam1Segs, Cam2: cam2Segs }, target)).toBe(true);
  });

  it('isPositionInPlayableGap for Cam1 at gap', () => {
    expect(isPositionInPlayableGap(cam1Segs, target)).toBe(true);
    expect(pickContainingSegment(cam1Segs, target)).toBeNull();
    expect(pickContainingPlayableSegment(cam1Segs, target)).toBeNull();
    expect(pickPlayableSegmentForPosition(cam1Segs, target)?.path).toBe('cam1_a.mp4');
  });

  it('Cam2 plays at gap time while Cam1 has no containing segment', () => {
    expect(pickContainingPlayableSegment(cam2Segs, target)?.path).toBe('cam2.mp4');
  });

  it('intersectPlayableCoverage is empty at Cam1 gap even when Cam2 records', () => {
    const viewFrom = target - 600;
    const viewTo = target + 600;
    const full = intersectPlayableCoverage({ Cam1: cam1Segs, Cam2: cam2Segs }, viewFrom, viewTo);
    expect(full.some((i) => i.from <= target && i.to >= target)).toBe(false);
    const cam2Only = intersectPlayableCoverage({ Cam2: cam2Segs }, viewFrom, viewTo);
    expect(cam2Only.some((i) => i.from <= target && i.to >= target)).toBe(true);
  });

  it('resolveUserSeekTarget without segments keeps raw click', () => {
    expect(resolveUserSeekTarget(target)).toBe(target);
  });
});

describe('playable union coverage', () => {
  const cam1Segs = [
    { path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true },
    { path: 'open.mp4', start_ts: 200, end_ts: 250, duration_ms: 50_000, playable: false },
  ];
  const cam2Segs = [{ path: 'b.mp4', start_ts: 150, end_ts: 300, duration_ms: 150_000, playable: true }];

  it('playableUnionCoverage excludes non-playable windows', () => {
    const union = playableUnionCoverage({ Cam1: cam1Segs }, 100, 300);
    expect(union).toEqual([{ from: 100, to: 200 }]);
    const multi = playableUnionCoverage({ Cam1: cam1Segs, Cam2: cam2Segs }, 100, 300);
    expect(multi.some((i) => i.from <= 220 && i.to >= 220)).toBe(true);
  });

  it('recordingUnionCoverage tracks in-progress only', () => {
    const rec = recordingUnionCoverage({ Cam1: cam1Segs }, 100, 300);
    expect(rec).toEqual([{ from: 200, to: 250 }]);
  });

  it('isPlayableAtPosition respects per-camera filter', () => {
    const byCam = { Cam1: cam1Segs, Cam2: cam2Segs };
    expect(isPlayableAtPosition(byCam, 225)).toBe(true);
    expect(isPlayableAtPosition(byCam, 225, 'Cam1')).toBe(false);
    expect(isPlayableAtPosition(byCam, 225, 'Cam2')).toBe(true);
  });

  it('snapUnionPositionToPlayable snaps gap to nearest playable', () => {
    const byCam = {
      Cam1: [{ path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true }],
      Cam2: [{ path: 'b.mp4', start_ts: 300, end_ts: 400, duration_ms: 100_000, playable: true }],
    };
    const snapped = snapUnionPositionToPlayable(byCam, 250);
    expect(snapped).toBeGreaterThanOrEqual(199);
    expect(snapped).toBeLessThanOrEqual(200);
  });

  it('nextPlayableStart finds earliest future segment', () => {
    const byCam = {
      Cam1: [{ path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true }],
      Cam2: [{ path: 'b.mp4', start_ts: 300, end_ts: 400, duration_ms: 100_000, playable: true }],
    };
    expect(nextPlayableStart(byCam, 250)).toBe(300);
  });

  it('snapTimelineSeek avoids detection snap into gap when segments provided', () => {
    const byCam = {
      Cam1: [{ path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true }],
    };
    const detectionTs = [250];
    const snapped = snapTimelineSeek(248, detectionTs, 100, 400, 500, byCam);
    expect(snapped).toBeLessThanOrEqual(200);
  });
});

describe('loaded interval coverage', () => {
  it('does not fill a gap when merging disjoint windows', () => {
    const evening = mergeLoadedIntervals([], { from: 20_000, to: 22_000 });
    const both = mergeLoadedIntervals(evening, { from: 8_000, to: 10_000 });
    expect(both).toEqual([
      { from: 8_000, to: 10_000 },
      { from: 20_000, to: 22_000 },
    ]);
    const midNeed = uncoveredIntervals({ from: 8_000, to: 22_000 }, both, { marginSec: 0 });
    expect(midNeed.length).toBe(1);
    expect(midNeed[0].from).toBe(10_000);
    expect(midNeed[0].to).toBe(20_000);
  });

  it('merges overlapping / touching windows', () => {
    const a = mergeLoadedIntervals([], { from: 100, to: 200 });
    const b = mergeLoadedIntervals(a, { from: 199, to: 300 });
    expect(b).toEqual([{ from: 100, to: 300 }]);
  });

  it('extent is min/max without implying contiguous coverage', () => {
    const intervals = [
      { from: 8_000, to: 10_000 },
      { from: 20_000, to: 22_000 },
    ];
    expect(intervalsExtent(intervals)).toEqual({ from: 8_000, to: 22_000 });
    expect(uncoveredIntervals({ from: 8_000, to: 22_000 }, intervals).length).toBeGreaterThan(0);
  });
});

describe('buildTimelineDateLabels', () => {
  it('always labels both edges of an intra-day view', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const from = start + 10 * 3600;
    const to = start + 12 * 3600;
    const labels = buildTimelineDateLabels(from, to);
    expect(labels[0]).toBe(from);
    expect(labels[labels.length - 1]).toBe(to);
    expect(labels.length).toBeGreaterThanOrEqual(2);
  });
});

describe('loaded interval coverage', () => {
  it('does not fill the gap when merging disjoint windows', () => {
    const evening = mergeLoadedIntervals([], { from: 20_000, to: 22_000 });
    const both = mergeLoadedIntervals(evening, { from: 8_000, to: 10_000 });
    expect(both).toEqual([
      { from: 8_000, to: 10_000 },
      { from: 20_000, to: 22_000 },
    ]);
    expect(intervalsExtent(both)).toEqual({ from: 8_000, to: 22_000 });
  });

  it('merges overlapping / touching windows', () => {
    const a = mergeLoadedIntervals([], { from: 100, to: 200 });
    const b = mergeLoadedIntervals(a, { from: 200, to: 300 });
    expect(b).toEqual([{ from: 100, to: 300 }]);
  });

  it('reports mid-day uncovered after evening+morning loads', () => {
    const loaded = mergeLoadedIntervals(
      mergeLoadedIntervals([], { from: 20_000, to: 22_000 }),
      { from: 8_000, to: 10_000 },
    );
    const gaps = uncoveredIntervals({ from: 8_000, to: 22_000 }, loaded);
    expect(gaps.length).toBe(1);
    expect(gaps[0].from).toBe(10_000);
    expect(gaps[0].to).toBe(20_000);
  });

  it('treats margin as soft coverage near edges', () => {
    const loaded = [{ from: 10_000, to: 12_000 }];
    const gaps = uncoveredIntervals({ from: 10_000 - 100, to: 12_000 + 100 }, loaded, {
      marginSec: 600,
    });
    expect(gaps).toEqual([]);
  });
});

describe('buildTimelineDateLabels', () => {
  it('always labels both edges of an intra-day view', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const from = start + 10 * 3600;
    const to = from + 2 * 3600;
    const labels = buildTimelineDateLabels(from, to);
    expect(labels[0]).toBe(from);
    expect(labels[labels.length - 1]).toBe(to);
    expect(labels.length).toBeGreaterThanOrEqual(2);
  });

  it('dedupes an edge that coincides with midnight', () => {
    const date = '2026-08-18';
    const { start } = dayBoundsLocal(date);
    const to = start + 2 * 3600;
    const labels = buildTimelineDateLabels(start, to);
    expect(labels.filter((x) => Math.abs(x - start) < 1)).toHaveLength(1);
    expect(labels).toContain(to);
  });
});
