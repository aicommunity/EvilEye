import type { PlaybackSegment } from '../../api';
import { isPlayableSegment } from './timelineMath';

/** Default max gap (sec) between decoded EOF and next segment start to auto-advance. */
export const EOF_ADVANCE_GAP_SLACK_SEC = 2;
/** Treat next.start as contiguous if within this of current index end. */
export const EOF_CONTIGUOUS_EPSILON_SEC = 0.5;

export type AdvanceOrStopAtEofResult =
  | { action: 'advanced'; next: PlaybackSegment }
  | { action: 'stopped' };

export function nextPlayableSegmentAfter(
  segs: PlaybackSegment[],
  current: PlaybackSegment | null,
): PlaybackSegment | null {
  if (!current || !segs.length) return null;
  const idx = segs.findIndex((s) => s.path === current.path);
  if (idx < 0) return null;
  for (let i = idx + 1; i < segs.length; i++) {
    if (isPlayableSegment(segs[i])) return segs[i];
  }
  return null;
}

/**
 * Decide playlist advance vs stop when the decoder hits / passes segment EOF.
 * Prefer advancing when a next playable segment is contiguous or within slack;
 * otherwise stop (caller must not keep emitting clock at the EOF pin).
 */
export function advanceOrStopAtEof(
  segs: PlaybackSegment[],
  current: PlaybackSegment | null,
  opts?: {
    /** Decoded media duration (sec); used when index end_ts overruns the mp4. */
    decodedDurationSec?: number;
    gapSlackSec?: number;
    epsilonSec?: number;
  },
): AdvanceOrStopAtEofResult {
  const next = nextPlayableSegmentAfter(segs, current);
  if (!current || !next) return { action: 'stopped' };

  const slack = Math.max(EOF_ADVANCE_GAP_SLACK_SEC, opts?.gapSlackSec ?? 0);
  const epsilon = opts?.epsilonSec ?? EOF_CONTIGUOUS_EPSILON_SEC;
  const decodedEnd =
    opts?.decodedDurationSec != null &&
    Number.isFinite(opts.decodedDurationSec) &&
    opts.decodedDurationSec > 0
      ? current.start_ts + opts.decodedDurationSec
      : current.end_ts;
  const gapToNext = next.start_ts - decodedEnd;
  // Contiguous to index end (handles slight overlap / tiny gap).
  const contiguousToIndex =
    next.start_ts >= current.end_ts - epsilon && next.start_ts <= current.end_ts + slack;
  // Contiguous to decoded EOF (index may overrun real mp4 duration).
  // Allow equality at slack boundary (gap of exactly 2s still advances).
  const withinSlack = gapToNext >= -epsilon && gapToNext <= slack;

  if (withinSlack || contiguousToIndex) {
    return { action: 'advanced', next };
  }
  return { action: 'stopped' };
}
