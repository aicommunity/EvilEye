import { describe, expect, it } from 'vitest';
import {
  applyPostLoadSnapIfNeeded,
  createUserSeekGuard,
  resolveUserSeekTarget,
} from './playbackSeek';
import type { PlaybackSegment } from '../../api';

describe('applyPostLoadSnapIfNeeded', () => {
  const segmentsByCam: Record<string, PlaybackSegment[]> = {
    Cam1: [{ path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true }],
  };

  it('skips snap shortly after user seek', () => {
    const guard = createUserSeekGuard();
    guard.markUserSeek();
    let pos = 150;
    applyPostLoadSnapIfNeeded(segmentsByCam, {
      initialT: null,
      getPosition: () => pos,
      seek: (s) => {
        pos = s;
      },
      guard,
    });
    expect(pos).toBe(150);
  });

  it('allows snap for deep link initialT', () => {
    const guard = createUserSeekGuard();
    guard.markUserSeek();
    let pos = 50;
    applyPostLoadSnapIfNeeded(segmentsByCam, {
      initialT: 50,
      getPosition: () => pos,
      seek: (s) => {
        pos = s;
      },
      guard,
    });
    expect(pos).toBe(100);
  });
});

describe('resolveUserSeekTarget', () => {
  const segmentsByCam: Record<string, PlaybackSegment[]> = {
    Cam1: [
      { path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true },
      { path: 'b.mp4', start_ts: 300, end_ts: 400, duration_ms: 100_000, playable: true },
    ],
  };

  it('keeps target inside playable union in playable mode', () => {
    expect(resolveUserSeekTarget(150, segmentsByCam, 'playable')).toBe(150);
  });

  it('does not snap gap seek in marker mode', () => {
    expect(resolveUserSeekTarget(250, segmentsByCam, 'marker')).toBe(250);
    expect(resolveUserSeekTarget(50, segmentsByCam, 'marker')).toBe(50);
  });

  it('snaps gap seek to nearest playable in playable mode', () => {
    expect(resolveUserSeekTarget(250, segmentsByCam, 'playable')).toBeGreaterThanOrEqual(199);
    expect(resolveUserSeekTarget(250, segmentsByCam, 'playable')).toBeLessThanOrEqual(200);
    expect(resolveUserSeekTarget(50, segmentsByCam, 'playable')).toBe(100);
  });
});
