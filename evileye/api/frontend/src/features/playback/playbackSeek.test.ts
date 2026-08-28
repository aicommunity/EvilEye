import { describe, expect, it } from 'vitest';
import { applyPostLoadSnapIfNeeded, createUserSeekGuard } from './playbackSeek';

describe('applyPostLoadSnapIfNeeded', () => {
  const segs = [
    { path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true },
  ];

  it('skips snap shortly after user seek', () => {
    const guard = createUserSeekGuard();
    guard.markUserSeek();
    let pos = 150;
    applyPostLoadSnapIfNeeded(segs, {
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
    applyPostLoadSnapIfNeeded(segs, {
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
