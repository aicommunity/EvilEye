import { describe, expect, it } from 'vitest';
import { mergeLiveCameraPoll } from './mergeLiveCameraPoll';

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
});
