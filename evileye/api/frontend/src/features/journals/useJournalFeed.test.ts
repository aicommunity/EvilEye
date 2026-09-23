import { describe, expect, it } from 'vitest';
import { shouldApplyJournalResult } from './useJournalFeed';

describe('shouldApplyJournalResult (B04)', () => {
  it('applies matching generation when not aborted', () => {
    expect(shouldApplyJournalResult(3, 3, false)).toBe(true);
  });

  it('ignores stale generation after fast filter switch', () => {
    // First load gen=1; switch bumps to gen=2 before response arrives.
    expect(shouldApplyJournalResult(1, 2, false)).toBe(false);
  });

  it('ignores aborted responses', () => {
    expect(shouldApplyJournalResult(5, 5, true)).toBe(false);
  });

  it('delayed responses + rapid switch simulation', async () => {
    let generation = 0;
    const applied: string[] = [];
    const load = async (label: string, delayMs: number, gen: number) => {
      await new Promise((r) => setTimeout(r, delayMs));
      if (shouldApplyJournalResult(gen, generation, false)) applied.push(label);
    };
    const g1 = ++generation;
    const p1 = load('camA', 40, g1);
    const g2 = ++generation;
    const p2 = load('camB', 5, g2);
    await Promise.all([p1, p2]);
    expect(applied).toEqual(['camB']);
  });
});
