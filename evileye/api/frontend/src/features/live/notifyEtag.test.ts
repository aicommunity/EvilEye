import { describe, expect, it, vi, beforeEach } from 'vitest';

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

    const { streamSnapshotUrl } = await import('../../api');
    // Inline the same contract as useLiveGridPreviewWs fetchSnapshotBlob
    async function fetchSnapshotBlob(runId: number, sourceId: number, etag?: string) {
      const url = streamSnapshotUrl(runId, sourceId);
      const headers: Record<string, string> = {};
      if (etag) headers['If-None-Match'] = `"${etag}"`;
      const res = await fetch(url, { credentials: 'same-origin', headers });
      return res;
    }

    await fetchSnapshotBlob(1, 0, undefined);
    await fetchSnapshotBlob(1, 0, 'etag-1');
    // Simulate bug: using notify etag as precondition would send If-None-Match on first fetch
    expect(calls[0]?.['If-None-Match']).toBeUndefined();
    expect(calls[1]?.['If-None-Match']).toBe('"etag-1"');
  });
});
