import { describe, expect, it } from 'vitest';
import {
  DEFAULT_TIMELINE_WINDOW_SEC,
  DETECTION_SNAP_MAX_SEC,
  clampViewToDayBounds,
  dayBoundsLocal,
  defaultTimelineView,
  snapTimelineSeek,
  snapUnixToDetections,
} from './timelineMath';

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
