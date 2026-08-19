import type { PlaybackSegment } from '../../api';

export const MIN_VIEW_SPAN_SEC = 120;
export const MAX_VIEW_SPAN_SEC = 48 * 3600;
export const DEFAULT_TIMELINE_WINDOW_SEC = 7200;
export const DAY_LOAD_BUFFER_SEC = 3 * 3600;
export const PAN_CLICK_SLOP_PX = 10;
export const DETECTION_SNAP_PX = 10;
/** Do not snap clicks across more than this many seconds (avoids sticky playhead when zoomed out). */
export const DETECTION_SNAP_MAX_SEC = 1.5;
/** Snap clicks to detection ticks only when the view is zoomed in this far. */
export const DETECTION_SNAP_VIEW_SPAN_SEC = 2 * 3600;

const TICK_STEPS_SEC = [60, 300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400];

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

export function formatPlaybackDateTime(tsSec: number): string {
  if (!Number.isFinite(tsSec) || tsSec <= 0) return '—';
  const d = new Date(tsSec * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function dayBoundsLocal(dateStr: string): { start: number; end: number } {
  const [y, m, d] = dateStr.split('-').map(Number);
  const start = new Date(y, (m || 1) - 1, d || 1, 0, 0, 0, 0).getTime() / 1000;
  const end = start + 86400;
  return { start, end };
}

/** Inclusive upper bound for timeline pan/zoom (avoids labelling the next calendar day at 00:00). */
export function dayViewUpperBound(dateStr: string): number {
  return dayBoundsLocal(dateStr).end - 1;
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
  const upper = dayViewUpperBound(dateStr);
  const windowSec = opts?.windowSec ?? DEFAULT_TIMELINE_WINDOW_SEC;
  const nowSec = opts?.nowSec ?? Date.now() / 1000;
  const dataFrom = opts?.dataFrom;
  const dataTo = opts?.dataTo;

  if (dataFrom != null && dataTo != null && dataTo > dataFrom) {
    const dataSpan = dataTo - dataFrom;
    const daySpan = upper - start + 1;
    if (dataSpan < daySpan * 0.85) {
      const pad = Math.max(900, dataSpan * 0.12);
      const vf = Math.max(start, dataFrom - pad);
      const vt = Math.min(upper, dataTo + pad);
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
): { viewFrom: number; viewTo: number } {
  const { start } = dayBoundsLocal(dateStr);
  const upper = dayViewUpperBound(dateStr);
  const daySpan = upper - start + 1;
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

export function mergeSegments(prev: PlaybackSegment[], next: PlaybackSegment[]): PlaybackSegment[] {
  const byPath = new Map<string, PlaybackSegment>();
  for (const s of prev) byPath.set(s.path, s);
  for (const s of next) byPath.set(s.path, s);
  return Array.from(byPath.values()).sort((a, b) => a.start_ts - b.start_ts);
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
