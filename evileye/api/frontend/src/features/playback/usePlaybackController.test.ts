import { describe, expect, it } from 'vitest';
import { createUserSeekGuard } from './playbackSeek';

describe('user seek guard', () => {
  it('blocks post-load snap for 5s after markUserSeek', () => {
    const guard = createUserSeekGuard();
    guard.markUserSeek();
    expect(guard.shouldApplyPostLoadSnap(null)).toBe(false);
  });

  it('always allows snap when initialT is set', () => {
    const guard = createUserSeekGuard();
    guard.markUserSeek();
    expect(guard.shouldApplyPostLoadSnap(12345)).toBe(true);
  });
});

describe('usePlaybackController user seek (unit)', () => {
  it('documents USER_SEEK_BLOCK_MS behaviour via guard timing', () => {
    const guard = createUserSeekGuard();
    expect(guard.shouldApplyPostLoadSnap(null)).toBe(true);
    guard.markUserSeek();
    expect(guard.shouldApplyPostLoadSnap(null)).toBe(false);
  });
});
