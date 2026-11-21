import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StreamMetadata } from '../../api';
import {
  contentSequenceKey,
  EMPTY_OBJECTS_HOLD_MS,
  METADATA_HARD_CLEAR_MS,
  METADATA_TTL_MS,
  RunMetadataStore,
} from './useRunMetadataWs';

function payload(
  partial: Partial<StreamMetadata> & { source_id?: number | null },
): StreamMetadata {
  return {
    source_id: partial.source_id ?? 0,
    objects: partial.objects ?? [{ object_id: 1, bbox: [0.1, 0.1, 0.2, 0.2] }],
    zones: partial.zones ?? [],
    signalization: partial.signalization ?? false,
    ...partial,
  } as StreamMetadata;
}

describe('contentSequenceKey', () => {
  it('prefers frame_id', () => {
    const key = contentSequenceKey({ source_id: 0, frame_id: 42 } as StreamMetadata);
    expect(key).toBe('f:0:42');
  });

  it('falls back to timestamp', () => {
    const key = contentSequenceKey({
      source_id: 1,
      timestamp: 1234.567,
    } as StreamMetadata);
    expect(key).toBe('t:1:1234.567');
  });
});

describe('RunMetadataStore freshness', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('window', {
      setInterval: (fn: () => void, ms?: number) =>
        setInterval(fn, ms ?? 500) as unknown as number,
      clearInterval: (id: number) => clearInterval(id),
      setTimeout: (fn: () => void, ms?: number) =>
        setTimeout(fn, ms ?? 0) as unknown as number,
      clearTimeout: (id: number) => clearTimeout(id),
      location: { protocol: 'http:', host: 'localhost' },
    });
    vi.stubGlobal(
      'WebSocket',
      vi.fn(() => ({
        close: vi.fn(),
        readyState: 0,
      })),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('does not extend TTL on duplicate frame_id poll', () => {
    const store = new RunMetadataStore(7);
    const updates: StreamMetadata[] = [];
    store.subscribe(0, (p) => updates.push(p));

    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 100 }));
    expect(store.isFresh(0)).toBe(true);

    vi.advanceTimersByTime(3000);
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 100 }));
    expect(store.isFresh(0)).toBe(true);

    vi.advanceTimersByTime(1500);
    store.runFreshnessCheckForTest();
    expect(store.isFresh(0)).toBe(false);
    const last = updates[updates.length - 1];
    expect(last.objects?.length).toBeGreaterThan(0);
  });

  it('resets TTL when frame_id changes', () => {
    const store = new RunMetadataStore(7);
    store.subscribe(0, () => {});

    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 100 }));
    vi.advanceTimersByTime(3000);
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 101 }));

    vi.advanceTimersByTime(3000);
    expect(store.isFresh(0)).toBe(true);
  });

  it('holds objects after soft TTL and clears after hard clear', () => {
    const store = new RunMetadataStore(7);
    const updates: StreamMetadata[] = [];
    store.subscribe(0, (p) => updates.push(p));
    store.subscribeFreshness(0, () => {});

    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 50 }));
    expect(updates[0]?.objects?.length).toBeGreaterThan(0);

    vi.advanceTimersByTime(METADATA_TTL_MS + 600);
    store.runFreshnessCheckForTest();
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 50 }));
    expect(store.isFresh(0)).toBe(false);
    expect(updates[updates.length - 1]?.objects?.length).toBeGreaterThan(0);

    vi.advanceTimersByTime(METADATA_HARD_CLEAR_MS);
    store.runFreshnessCheckForTest();
    expect(updates[updates.length - 1]?.objects).toEqual([]);
  });

  it('holds objects across empty sequence until EMPTY_OBJECTS_HOLD_MS', () => {
    const store = new RunMetadataStore(7);
    const updates: StreamMetadata[] = [];
    store.subscribe(0, (p) => updates.push(p));

    const heldObj = { object_id: 1, bbox: [0.1, 0.1, 0.2, 0.2] as [number, number, number, number] };
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 50, objects: [heldObj] }));
    store.pushPayloadForTest(
      payload({
        source_id: 0,
        frame_id: 51,
        objects: [],
        zones: [{ zone_id: 9 } as never],
      }),
    );
    const duringHold = updates[updates.length - 1];
    expect(duringHold?.objects).toEqual([heldObj]);
    expect(duringHold?.zones).toEqual([{ zone_id: 9 }]);

    vi.advanceTimersByTime(EMPTY_OBJECTS_HOLD_MS);
    expect(updates[updates.length - 1]?.objects).toEqual([]);
    expect(updates[updates.length - 1]?.zones).toEqual([{ zone_id: 9 }]);
  });

  it('cancels empty hold when a non-empty sequence arrives', () => {
    const store = new RunMetadataStore(7);
    const updates: StreamMetadata[] = [];
    store.subscribe(0, (p) => updates.push(p));

    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 50 }));
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 51, objects: [] }));
    expect(updates[updates.length - 1]?.objects?.length).toBeGreaterThan(0);

    const next = { object_id: 2, bbox: [0.3, 0.3, 0.4, 0.4] as [number, number, number, number] };
    store.pushPayloadForTest(payload({ source_id: 0, frame_id: 52, objects: [next] }));
    expect(updates[updates.length - 1]?.objects).toEqual([next]);

    vi.advanceTimersByTime(EMPTY_OBJECTS_HOLD_MS + 100);
    expect(updates[updates.length - 1]?.objects).toEqual([next]);
  });
});
