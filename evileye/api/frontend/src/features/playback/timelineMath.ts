import type { PlaybackSegment } from '../../api';

/** Closest zoom: full timeline width covers at least this many seconds. */
export const MIN_VIEW_SPAN_SEC = 5 * 60;
export const MAX_VIEW_SPAN_SEC = 24 * 3600;
export const DEFAULT_TIMELINE_WINDOW_SEC = 7200;
export const DAY_LOAD_BUFFER_SEC = 3 * 3600;
export const PAN_CLICK_SLOP_PX = 10;
export const DETECTION_SNAP_PX = 10;
/** Do not snap clicks across more than this many seconds (avoids sticky playhead when zoomed out). */
export const DETECTION_SNAP_MAX_SEC = 1.5;
/** Snap clicks to detection ticks only when the view is zoomed in this far. */
export const DETECTION_SNAP_VIEW_SPAN_SEC = 2 * 3600;

const TICK_STEPS_SEC = [60, 300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400];

/** Visible span of a calendar day for zoom-out hard stop. */
export function dayViewSpanSec(dateStr: string, nowSec?: number): number {
  const { start } = dayBoundsLocal(dateStr);
  const upper = dayViewUpperBound(dateStr, nowSec);
  return Math.max(MIN_VIEW_SPAN_SEC, upper - start + 1);
}

export function clampView(
  viewFrom: number,
  viewTo: number,
  limits?: { min?: number; max?: number; minSpan?: number; maxSpan?: number },
): { viewFrom: number; viewTo: number } {
  let from = viewFrom;
  let to = viewTo;
  if (!(to > from)) {
    to = from + (limits?.minSpan ?? MIN_VIEW_SPAN_SEC);
  }
  let span = to - from;
  const minSpan = limits?.minSpan ?? MIN_VIEW_SPAN_SEC;
  const maxSpan = limits?.maxSpan ?? MAX_VIEW_SPAN_SEC;
  if (span < minSpan) {
    const mid = (from + to) / 2;
    from = mid - minSpan / 2;
    to = mid + minSpan / 2;
    span = minSpan;
  }
  if (span > maxSpan) {
    const mid = (from + to) / 2;
    from = mid - maxSpan / 2;
    to = mid + maxSpan / 2;
  }
  if (limits?.min != null && limits?.max != null) {
    const lo = limits.min;
    const hi = limits.max;
    const pad = Math.max(hi - lo, minSpan);
    if (from < lo - pad) {
      const d = lo - pad - from;
      from += d;
      to += d;
    }
    if (to > hi + pad) {
      const d = to - (hi + pad);
      from -= d;
      to -= d;
    }
  }
  return { viewFrom: from, viewTo: to };
}

export function zoomViewAt(
  viewFrom: number,
  viewTo: number,
  anchorUnix: number,
  factor: number,
  limits?: { minSpan?: number; maxSpan?: number; dataMin?: number; dataMax?: number },
): { viewFrom: number; viewTo: number } {
  const span = viewTo - viewFrom;
  if (!(span > 0) || !Number.isFinite(factor) || factor <= 0) {
    return { viewFrom, viewTo };
  }
  const ratio = Math.min(1, Math.max(0, (anchorUnix - viewFrom) / span));
  let nextSpan = span * factor;
  const minSpan = limits?.minSpan ?? MIN_VIEW_SPAN_SEC;
  const maxSpan = limits?.maxSpan ?? MAX_VIEW_SPAN_SEC;
  nextSpan = Math.min(maxSpan, Math.max(minSpan, nextSpan));
  const nextFrom = anchorUnix - ratio * nextSpan;
  const nextTo = nextFrom + nextSpan;
  return clampView(nextFrom, nextTo, {
    minSpan,
    maxSpan,
    min: limits?.dataMin,
    max: limits?.dataMax,
  });
}

/**
 * Wheel zoom constrained to a single calendar day.
 * Never crosses midnight (avoids accidental date switch → empty timeline).
 * When zooming out to the day span, snaps to exact [dayStart, dayUpper].
 */
export function zoomViewWithinDay(
  viewFrom: number,
  viewTo: number,
  anchorUnix: number,
  factor: number,
  dateStr: string,
  nowSec?: number,
): { viewFrom: number; viewTo: number } {
  const { start } = dayBoundsLocal(dateStr);
  const upper = dayViewUpperBound(dateStr, nowSec);
  const daySpan = dayViewSpanSec(dateStr, nowSec);
  const span = viewTo - viewFrom;
  if (!(span > 0) || !Number.isFinite(factor) || factor <= 0) {
    return { viewFrom, viewTo };
  }
  // Hard stops before computing a new window.
  if (factor > 1 && span >= daySpan - 1) {
    return { viewFrom: start, viewTo: upper };
  }
  if (factor < 1 && span <= MIN_VIEW_SPAN_SEC + 1) {
    return clampViewToDayBounds(viewFrom, viewTo, dateStr, nowSec);
  }

  const next = zoomViewAt(viewFrom, viewTo, anchorUnix, factor, {
    minSpan: MIN_VIEW_SPAN_SEC,
    maxSpan: daySpan,
  });
  let clamped = clampViewToDayBounds(next.viewFrom, next.viewTo, dateStr, nowSec);
  const nextSpan = clamped.viewTo - clamped.viewFrom;
  // Zoom-out that hits the day ceiling: lock to full day so the window stops jumping.
  if (factor > 1 && nextSpan >= daySpan - 1) {
    clamped = { viewFrom: start, viewTo: upper };
  }
  return clamped;
}

export function panView(
  viewFrom: number,
  viewTo: number,
  deltaSec: number,
  limits?: { dataMin?: number; dataMax?: number },
): { viewFrom: number; viewTo: number } {
  return clampView(viewFrom + deltaSec, viewTo + deltaSec, {
    min: limits?.dataMin,
    max: limits?.dataMax,
  });
}

/** Pan clamped to a single calendar day (no midnight cross / date switch). */
export function panViewWithinDay(
  viewFrom: number,
  viewTo: number,
  deltaSec: number,
  dateStr: string,
  nowSec?: number,
): { viewFrom: number; viewTo: number } {
  const shifted = panView(viewFrom, viewTo, deltaSec);
  return clampViewToDayBounds(shifted.viewFrom, shifted.viewTo, dateStr, nowSec);
}

export function unixAtClientX(
  clientX: number,
  rect: { left: number; width: number },
  viewFrom: number,
  viewTo: number,
): number {
  const span = viewTo - viewFrom;
  if (!(span > 0) || !(rect.width > 0)) return viewFrom;
  const x = (clientX - rect.left) / rect.width;
  return viewFrom + Math.min(1, Math.max(0, x)) * span;
}

/** Snap a click to the nearest detection tick if it is within snapPx on the timeline. */
export function snapUnixToDetections(
  unix: number,
  detectionTs: number[],
  viewFrom: number,
  viewTo: number,
  widthPx: number,
  snapPx = DETECTION_SNAP_PX,
): number {
  if (!detectionTs.length || !(widthPx > 0) || viewTo <= viewFrom || !Number.isFinite(unix)) {
    return unix;
  }
  const secPerPx = (viewTo - viewFrom) / widthPx;
  const maxDt = Math.min(snapPx * secPerPx, DETECTION_SNAP_MAX_SEC);
  let best: number | null = null;
  let bestDt = Infinity;
  for (const ts of detectionTs) {
    if (!Number.isFinite(ts)) continue;
    const dt = Math.abs(ts - unix);
    if (dt < bestDt) {
      bestDt = dt;
      best = ts;
    } else if (ts > unix && dt > bestDt) {
      break;
    }
  }
  if (best != null && bestDt <= maxDt) return best;
  return unix;
}

export function snapTimelineSeek(
  unix: number,
  detectionTs: number[],
  viewFrom: number,
  viewTo: number,
  widthPx: number,
): number {
  if (viewTo - viewFrom >= DETECTION_SNAP_VIEW_SPAN_SEC) return unix;
  return snapUnixToDetections(unix, detectionTs, viewFrom, viewTo, widthPx);
}

export function localDateString(tsSec: number): string {
  const d = new Date(tsSec * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function formatPlaybackTime(tsSec: number): string {
  if (!Number.isFinite(tsSec) || tsSec <= 0) return '—';
  const d = new Date(tsSec * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** @deprecated Prefer formatPlaybackTime in toolbar; keep for tests/tooltips without i18n. */
export function formatPlaybackDateTime(tsSec: number): string {
  if (!Number.isFinite(tsSec) || tsSec <= 0) return '—';
  const d = new Date(tsSec * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function dayBoundsLocal(dateStr: string): { start: number; end: number } {
  const [y, m, d] = dateStr.split('-').map(Number);
  const start = new Date(y, (m || 1) - 1, d || 1, 0, 0, 0, 0).getTime() / 1000;
  const end = start + 86400;
  return { start, end };
}

export function shiftLocalDate(dateStr: string, deltaDays: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1, 12, 0, 0, 0);
  dt.setDate(dt.getDate() + deltaDays);
  return localDateString(dt.getTime() / 1000);
}

/** Inclusive upper bound for timeline pan/zoom; for today clamps to now. */
export function dayViewUpperBound(dateStr: string, nowSec?: number): number {
  const dayEnd = dayBoundsLocal(dateStr).end - 1;
  const now = nowSec ?? Date.now() / 1000;
  if (localDateString(now) === dateStr) {
    return Math.min(dayEnd, now);
  }
  return dayEnd;
}

/** Default zoomed timeline window — never the full calendar day (pan/zoom need headroom). */
export function defaultTimelineView(
  dateStr: string,
  opts?: {
    dataFrom?: number | null;
    dataTo?: number | null;
    nowSec?: number;
    windowSec?: number;
  },
): { viewFrom: number; viewTo: number } {
  const { start } = dayBoundsLocal(dateStr);
  const nowSec = opts?.nowSec ?? Date.now() / 1000;
  const upper = dayViewUpperBound(dateStr, nowSec);
  const windowSec = opts?.windowSec ?? DEFAULT_TIMELINE_WINDOW_SEC;
  const dataFrom = opts?.dataFrom;
  const dataTo = opts?.dataTo;

  if (dataFrom != null && dataTo != null && dataTo > dataFrom) {
    const dataSpan = dataTo - dataFrom;
    const daySpan = upper - start + 1;
    // Do not pad the viewport past known data — empty edges confuse the timeline.
    if (dataSpan < daySpan * 0.85) {
      const vf = Math.max(start, dataFrom);
      const vt = Math.min(upper, dataTo);
      return { viewFrom: vf, viewTo: Math.max(vf + MIN_VIEW_SPAN_SEC, vt) };
    }
    const end = Math.min(upper, dataTo);
    const vf = Math.max(start, end - windowSec);
    return { viewFrom: vf, viewTo: Math.max(vf + MIN_VIEW_SPAN_SEC, end) };
  }

  if (localDateString(nowSec) === dateStr) {
    const to = Math.min(upper, nowSec);
    const vf = Math.max(start, to - windowSec);
    return { viewFrom: vf, viewTo: Math.max(vf + MIN_VIEW_SPAN_SEC, to) };
  }
  const vf = Math.max(start, upper - windowSec);
  return { viewFrom: vf, viewTo: upper };
}

export function segmentIntersectsDay(seg: PlaybackSegment, dateStr: string): boolean {
  const { start, end } = dayBoundsLocal(dateStr);
  return seg.end_ts >= start && seg.start_ts < end;
}

export function clampViewToDayBounds(
  viewFrom: number,
  viewTo: number,
  dateStr: string,
  nowSec?: number,
): { viewFrom: number; viewTo: number } {
  const { start } = dayBoundsLocal(dateStr);
  const upper = dayViewUpperBound(dateStr, nowSec);
  const daySpan = Math.max(MIN_VIEW_SPAN_SEC, upper - start + 1);
  let { viewFrom: from, viewTo: to } = clampView(viewFrom, viewTo, {
    minSpan: MIN_VIEW_SPAN_SEC,
    maxSpan: Math.min(MAX_VIEW_SPAN_SEC, daySpan),
  });
  const span = to - from;
  if (from < start) {
    from = start;
    to = start + span;
  }
  if (to > upper) {
    to = upper;
    from = upper - span;
  }
  if (from < start) from = start;
  return { viewFrom: from, viewTo: to };
}

/**
 * Clamp/pan across day boundaries. Moving into the past switches date;
 * moving past "now" on today is hard-clamped.
 */
export function resolveTimelineViewChange(
  viewFrom: number,
  viewTo: number,
  dateStr: string,
  nowSec?: number,
): { date: string; viewFrom: number; viewTo: number; dateChanged: boolean } {
  const now = nowSec ?? Date.now() / 1000;
  const today = localDateString(now);
  const { start } = dayBoundsLocal(dateStr);
  const upper = dayViewUpperBound(dateStr, now);

  if (viewFrom < start) {
    const prev = shiftLocalDate(dateStr, -1);
    const clamped = clampViewToDayBounds(viewFrom, viewTo, prev, now);
    return { date: prev, viewFrom: clamped.viewFrom, viewTo: clamped.viewTo, dateChanged: true };
  }

  if (dateStr >= today) {
    const date = today;
    const clamped = clampViewToDayBounds(viewFrom, viewTo, date, now);
    return { date, viewFrom: clamped.viewFrom, viewTo: clamped.viewTo, dateChanged: date !== dateStr };
  }

  if (viewTo > upper) {
    const next = shiftLocalDate(dateStr, 1);
    const date = next > today ? today : next;
    const clamped = clampViewToDayBounds(viewFrom, viewTo, date, now);
    return { date, viewFrom: clamped.viewFrom, viewTo: clamped.viewTo, dateChanged: date !== dateStr };
  }

  const clamped = clampViewToDayBounds(viewFrom, viewTo, dateStr, now);
  return { date: dateStr, viewFrom: clamped.viewFrom, viewTo: clamped.viewTo, dateChanged: false };
}

/** Clip a time range to the visible viewport; null if no intersection. */
export function clipRangeToView(
  startTs: number,
  endTs: number,
  viewFrom: number,
  viewTo: number,
): { leftPct: number; widthPct: number } | null {
  const span = viewTo - viewFrom;
  if (!(span > 0) || endTs <= viewFrom || startTs >= viewTo) return null;
  const leftSec = Math.max(startTs, viewFrom);
  const rightSec = Math.min(endTs, viewTo);
  if (rightSec <= leftSec) return null;
  return {
    leftPct: ((leftSec - viewFrom) / span) * 100,
    widthPct: ((rightSec - leftSec) / span) * 100,
  };
}

export function mergeSegments(prev: PlaybackSegment[], next: PlaybackSegment[]): PlaybackSegment[] {
  const byPath = new Map<string, PlaybackSegment>();
  for (const s of prev) byPath.set(s.path, s);
  for (const s of next) byPath.set(s.path, s);
  return Array.from(byPath.values()).sort((a, b) => a.start_ts - b.start_ts);
}

export function isPlayableSegment(seg: PlaybackSegment): boolean {
  return seg.playable !== false;
}

export function pickContainingSegment(segs: PlaybackSegment[], positionSec: number): PlaybackSegment | null {
  return segs.find((s) => positionSec >= s.start_ts && positionSec <= s.end_ts) ?? null;
}

export function pickSegmentNear(segs: PlaybackSegment[], positionSec: number): PlaybackSegment | null {
  if (!segs.length) return null;
  const containing = pickContainingSegment(segs, positionSec);
  if (containing) return containing;
  let best = segs[0];
  let bestDist = Infinity;
  for (const s of segs) {
    const dist =
      positionSec < s.start_ts
        ? s.start_ts - positionSec
        : positionSec > s.end_ts
          ? positionSec - s.end_ts
          : 0;
    if (dist < bestDist) {
      bestDist = dist;
      best = s;
    }
  }
  return best;
}

/** Nearest browser-playable segment for media src (skips in-progress splitmux files). */
export function pickPlayableSegmentForPosition(segs: PlaybackSegment[], positionSec: number): PlaybackSegment | null {
  const playable = segs.filter(isPlayableSegment);
  if (!playable.length) return null;
  const containing = pickContainingSegment(playable, positionSec);
  if (containing) return containing;
  return pickSegmentNear(playable, positionSec);
}

export function pickLastPlayableSegment(segs: PlaybackSegment[]): PlaybackSegment | null {
  const playable = segs.filter(isPlayableSegment);
  return playable.length ? playable[playable.length - 1] : null;
}

/** Snap playhead into a playable segment when position sits in a recording-only window. */
export function snapPositionToPlayable(segs: PlaybackSegment[], positionSec: number): number {
  if (!segs.length) return positionSec;
  const containing = pickContainingSegment(segs, positionSec);
  if (containing && isPlayableSegment(containing)) {
    // Index end_ts often overruns the real mp4 (tens of seconds). Landing in that
    // phantom tail freezes HTMLVideoElement seeks during play.
    const span = Math.max(0, containing.end_ts - containing.start_ts);
    const pad = Math.min(60, Math.max(2, span * 0.04));
    const safeEnd = containing.end_ts - pad;
    if (positionSec > safeEnd) return Math.max(containing.start_ts, safeEnd);
    return positionSec;
  }
  const target = pickPlayableSegmentForPosition(segs, positionSec);
  if (target) {
    if (positionSec > target.end_ts) {
      const span = Math.max(0, target.end_ts - target.start_ts);
      const pad = Math.min(60, Math.max(2, span * 0.04));
      return Math.max(target.start_ts, target.end_ts - pad);
    }
    if (positionSec < target.start_ts) return target.start_ts;
    const span = Math.max(0, target.end_ts - target.start_ts);
    const pad = Math.min(60, Math.max(2, span * 0.04));
    const safeEnd = target.end_ts - pad;
    if (positionSec > safeEnd) return Math.max(target.start_ts, safeEnd);
    return positionSec;
  }
  const last = pickLastPlayableSegment(segs);
  if (last) {
    const span = Math.max(0, last.end_ts - last.start_ts);
    const pad = Math.min(60, Math.max(2, span * 0.04));
    return Math.max(last.start_ts, Math.min(positionSec, last.end_ts - pad));
  }
  return positionSec;
}

export function isPositionInRecordingSegment(segs: PlaybackSegment[], positionSec: number): boolean {
  const containing = pickContainingSegment(segs, positionSec);
  return containing != null && !isPlayableSegment(containing);
}

/** Build ~6–10 nicely spaced unix-second ticks in [from, to]. */
export function buildTimelineTicks(from: number, to: number): number[] {
  const span = to - from;
  if (!(span > 0)) return [];
  let step = TICK_STEPS_SEC[TICK_STEPS_SEC.length - 1];
  for (const candidate of TICK_STEPS_SEC) {
    const count = span / candidate;
    if (count <= 10) {
      step = candidate;
      break;
    }
  }
  for (const candidate of TICK_STEPS_SEC) {
    if (candidate > step) break;
    const count = span / candidate;
    if (count >= 4 && count <= 10) {
      step = candidate;
    }
  }
  const first = Math.ceil(from / step) * step;
  const ticks: number[] = [];
  for (let ts = first; ts <= to + 1e-6; ts += step) {
    if (ts >= from - 1e-6 && ts <= to + 1e-6) ticks.push(ts);
  }
  if (!ticks.length || ticks[0] > from + step * 0.25) {
    ticks.unshift(from);
  }
  if (ticks[ticks.length - 1] < to - step * 0.25) {
    ticks.push(to);
  }
  const out: number[] = [];
  for (const ts of ticks) {
    if (!out.length || Math.abs(ts - out[out.length - 1]) > step * 0.2) out.push(ts);
  }
  return out;
}

/** Local-midnight unix timestamps that fall inside / on the edges of [from, to]. */
export function buildTimelineDateBoundaries(from: number, to: number): number[] {
  if (!(to > from) || !Number.isFinite(from) || !Number.isFinite(to)) return [];
  const out: number[] = [];
  const startDate = localDateString(from);
  const endDate = localDateString(to);
  let cursor = startDate;
  // Cap iterations to avoid runaway on bad inputs.
  for (let i = 0; i < 8; i += 1) {
    const { start } = dayBoundsLocal(cursor);
    if (start >= from - 1e-6 && start <= to + 1e-6) out.push(start);
    if (cursor >= endDate) break;
    cursor = shiftLocalDate(cursor, 1);
  }
  return out;
}

export type TimeInterval = { from: number; to: number };

const LOADED_TOUCH_EPS_SEC = 1;
const MIN_UNCOVERED_SEC = 1;

/** Merge overlapping / touching intervals; never fills a real gap. */
export function mergeLoadedIntervals(
  intervals: TimeInterval[],
  added: TimeInterval,
  touchEps = LOADED_TOUCH_EPS_SEC,
): TimeInterval[] {
  if (!(added.to > added.from) || !Number.isFinite(added.from) || !Number.isFinite(added.to)) {
    return intervals.filter((i) => i.to > i.from).sort((a, b) => a.from - b.from);
  }
  const all = [...intervals, added]
    .filter((i) => i.to > i.from && Number.isFinite(i.from) && Number.isFinite(i.to))
    .sort((a, b) => a.from - b.from);
  const out: TimeInterval[] = [];
  for (const cur of all) {
    const last = out[out.length - 1];
    if (!last || cur.from > last.to + touchEps) {
      out.push({ from: cur.from, to: cur.to });
    } else {
      last.to = Math.max(last.to, cur.to);
    }
  }
  return out;
}

/** Subtract loaded coverage from need; returns uncovered gaps (sorted). */
export function uncoveredIntervals(
  need: TimeInterval,
  loaded: TimeInterval[],
  opts?: { marginSec?: number; minGapSec?: number },
): TimeInterval[] {
  if (!(need.to > need.from)) return [];
  const margin = opts?.marginSec ?? 0;
  const minGap = opts?.minGapSec ?? MIN_UNCOVERED_SEC;
  const cov = loaded
    .map((i) => ({ from: i.from - margin, to: i.to + margin }))
    .filter((i) => i.to > i.from)
    .sort((a, b) => a.from - b.from);
  let gaps: TimeInterval[] = [{ from: need.from, to: need.to }];
  for (const c of cov) {
    const next: TimeInterval[] = [];
    for (const g of gaps) {
      if (c.to <= g.from || c.from >= g.to) {
        next.push(g);
        continue;
      }
      if (c.from > g.from) next.push({ from: g.from, to: Math.min(g.to, c.from) });
      if (c.to < g.to) next.push({ from: Math.max(g.from, c.to), to: g.to });
    }
    gaps = next;
  }
  return gaps.filter((g) => g.to - g.from >= minGap);
}

export function intervalsExtent(intervals: TimeInterval[]): TimeInterval | null {
  const ok = intervals.filter((i) => i.to > i.from);
  if (!ok.length) return null;
  return {
    from: Math.min(...ok.map((i) => i.from)),
    to: Math.max(...ok.map((i) => i.to)),
  };
}

/**
 * Midnight boundaries inside the view plus always-on edge labels at from/to.
 * Dedupes an edge that coincides with an existing midnight tick.
 */
export function buildTimelineDateLabels(from: number, to: number): number[] {
  if (!(to > from) || !Number.isFinite(from) || !Number.isFinite(to)) return [];
  const midnights = buildTimelineDateBoundaries(from, to);
  const out: number[] = [...midnights];
  const nearExisting = (ts: number) => out.some((x) => Math.abs(x - ts) < 60);
  if (!nearExisting(from)) out.push(from);
  if (!nearExisting(to)) out.push(to);
  return out.sort((a, b) => a - b);
}
