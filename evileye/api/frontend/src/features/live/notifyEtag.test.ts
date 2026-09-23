import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fetchSnapshotBlob, frameKey } from './useLiveGridPreviewWs';

describe('notify etag precondition (A06)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('first notify fetch omits If-None-Match; second uses stored etag only', async () => {
    const calls: Array<Record<string, string> | undefined> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        calls.push(init?.headers as Record<string, string> | undefined);
        return {
          status: 200,
          ok: true,
          headers: { get: (k: string) => (k.toLowerCase() === 'etag' ? '"etag-1"' : null) },
          blob: async () => new Blob([new Uint8Array([1, 2, 3])]),
        };
      }),
    );

    await fetchSnapshotBlob(1, 0, undefined);
    await fetchSnapshotBlob(1, 0, 'etag-1');
    expect(calls[0]?.['If-None-Match']).toBeUndefined();
    expect(calls[1]?.['If-None-Match']).toBe('"etag-1"');
  });

  it('returns null on 304', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        status: 304,
        ok: false,
        headers: { get: () => null },
        blob: async () => new Blob(),
      })),
    );
    expect(await fetchSnapshotBlob(1, 0, 'etag-1')).toBeNull();
  });
});

describe('multi-run frame keys (A07)', () => {
  it('same source_id under different runs stay distinct', () => {
    const a = frameKey(10, 0);
    const b = frameKey(20, 0);
    expect(a).not.toBe(b);
    const map = new Map<string, string>();
    map.set(a, 'run10');
    map.set(b, 'run20');
    expect(map.get(frameKey(10, 0))).toBe('run10');
    expect(map.get(frameKey(20, 0))).toBe('run20');
  });
});
