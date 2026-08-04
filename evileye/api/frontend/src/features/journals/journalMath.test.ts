import { describe, expect, it } from 'vitest';
import { letterboxRect, mergePrependRows, rowKey } from './journalMath';

describe('journalMath', () => {
  it('rowKey prefers row_key', () => {
    expect(rowKey({ row_key: 'a' } as never)).toBe('a');
  });

  it('mergePrependRows prepends new keys', () => {
    const existing = [{ row_key: 'b' }, { row_key: 'c' }] as never[];
    const incoming = [{ row_key: 'a' }, { row_key: 'b' }] as never[];
    const merged = mergePrependRows(existing, incoming);
    expect(merged.rows.map(rowKey)).toEqual(['a', 'b', 'c']);
    expect(merged.added).toBe(1);
  });

  it('letterboxRect centers content', () => {
    const box = letterboxRect(200, 100, 100, 100);
    expect(box.width).toBe(100);
    expect(box.height).toBe(100);
    expect(box.left).toBe(50);
    expect(box.top).toBe(0);
  });
});
