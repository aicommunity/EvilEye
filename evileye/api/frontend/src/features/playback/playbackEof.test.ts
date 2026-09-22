import { describe, expect, it } from 'vitest';
import type { PlaybackSegment } from '../../api';
import { advanceOrStopAtEof, nextPlayableSegmentAfter } from './playbackEof';

function seg(path: string, start: number, end: number, playable = true): PlaybackSegment {
  return {
    path,
    start_ts: start,
    end_ts: end,
    duration_ms: Math.max(0, (end - start) * 1000),
    playable,
  };
}

describe('advanceOrStopAtEof', () => {
  it('advances to next contiguous playable segment', () => {
    const a = seg('a.mp4', 1000, 1180);
    const b = seg('b.mp4', 1180, 1360);
    const r = advanceOrStopAtEof([a, b], a, { decodedDurationSec: 179.9 });
    expect(r).toEqual({ action: 'advanced', next: b });
  });

  it('advances when gap is under slack even if index end overruns', () => {
    const a = seg('a.mp4', 1000, 1200);
    const b = seg('b.mp4', 1182, 1360);
    const r = advanceOrStopAtEof([a, b], a, { decodedDurationSec: 180 });
    expect(r.action).toBe('advanced');
  });

  it('stops when there is no next playable segment', () => {
    const a = seg('a.mp4', 1000, 1180);
    expect(advanceOrStopAtEof([a], a)).toEqual({ action: 'stopped' });
  });

  it('stops across a large gap (do not jump hours ahead)', () => {
    const a = seg('a.mp4', 1000, 1180);
    const b = seg('b.mp4', 5000, 5180);
    expect(advanceOrStopAtEof([a, b], a, { decodedDurationSec: 180 })).toEqual({
      action: 'stopped',
    });
  });

  it('skips non-playable gaps to the next playable within slack', () => {
    const a = seg('a.mp4', 1000, 1180);
    const gap = seg('gap.mp4', 1180, 1181, false);
    const b = seg('b.mp4', 1181, 1360);
    const next = nextPlayableSegmentAfter([a, gap, b], a);
    expect(next?.path).toBe('b.mp4');
    expect(advanceOrStopAtEof([a, gap, b], a, { decodedDurationSec: 180 }).action).toBe(
      'advanced',
    );
  });
});
