import { describe, expect, it, vi } from 'vitest';
import { mergeLiveCameraPoll, resetLiveCameraCache } from './mergeLiveCameraPoll';

describe('mergeLiveCameraPoll', () => {
  const cam = { run_id: 1, source_id: 0 };

  it('keeps last good on first empty poll', () => {
    const d = mergeLiveCameraPoll([], [cam], [cam], 0, 2);
    expect(d.cameras).toEqual([cam]);
    expect(d.emptyStreak).toBe(1);
    expect(d.cleared).toBe(false);
  });

  it('clears after grace empty polls', () => {
    const d1 = mergeLiveCameraPoll([], [cam], [cam], 0, 2);
    const d2 = mergeLiveCameraPoll([], d1.cameras, d1.lastGood, d1.emptyStreak, 2);
    expect(d2.cameras).toEqual([]);
    expect(d2.lastGood).toEqual([]);
    expect(d2.cleared).toBe(true);
  });

  it('resets streak on non-empty', () => {
    const d = mergeLiveCameraPoll([cam], [], [], 5, 2);
    expect(d.cameras).toEqual([cam]);
    expect(d.emptyStreak).toBe(0);
  });

  it('writes empty when cleared (cache caller contract)', () => {
    const d = mergeLiveCameraPoll([], [cam], [cam], 1, 2);
    expect(d.cleared).toBe(true);
    expect(d.cameras).toEqual([]);
  });
});

describe('resetLiveCameraCache', () => {
  it('invalidates live cameras key and returns empty grace state', () => {
    const invalidate = vi.fn();
    const reset = resetLiveCameraCache(invalidate);
    expect(invalidate).toHaveBeenCalledWith('state:cameras:current');
    expect(reset).toEqual({ lastGood: [], emptyStreak: 0 });
  });
});
