/** Audit reproductions: passing means defects observed, not release acceptance.
 * Needs React 18.3.1 + react-test-renderer 18.3.1 + frontend Vitest.
 * Uses actual hooks/stores and React effects; only network/browser surfaces are fake.
 */
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { afterAll, afterEach, beforeEach, expect, it, vi } from 'vitest';
import { writeFileSync } from 'node:fs';
import { useDetectionIndex } from '../../evileye/api/frontend/src/features/playback/useDetectionIndex';
import { useLiveGridPreviewWs } from '../../evileye/api/frontend/src/features/live/useLiveGridPreviewWs';
import { RunMetadataStore } from '../../evileye/api/frontend/src/features/live/useRunMetadataWs';
import { useJournalFeed } from '../../evileye/api/frontend/src/features/journals/useJournalFeed';
import { bumpAuthScope, _resetAuthScopeForTests } from '../../evileye/api/frontend/src/auth/authScope';
import { cacheClear } from '../../evileye/api/frontend/src/api/dataCache';

const mocks = vi.hoisted(() => ({ detections: vi.fn(), request: vi.fn(), grouped: vi.fn() }));
vi.mock('../../evileye/api/frontend/src/api', async () => {
  const cache = await import('../../evileye/api/frontend/src/api/dataCache');
  return { ...cache, ApiError: class extends Error {},
    playbackApi: { detections: mocks.detections }, request: mocks.request,
    streamMetadataWsUrl: (rid: number) => `ws://audit/${rid}`,
    streamSnapshotUrl: (rid: number, sid: number) => `/snapshot/${rid}/${sid}`,
    journalsApi: { eventsGrouped: mocks.grouped, objectsGrouped: mocks.grouped },
    formatApiError: (e: Error) => e.message,
  };
});
vi.mock('../../evileye/api/frontend/src/diagnostics/clientTelemetry', () => ({ clientTelemetryLog: vi.fn() }));
vi.mock('../../evileye/api/frontend/src/i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1;
  onopen: any; onmessage: any; onclose: any; onerror: any;
  sent: string[] = [];
  constructor(public url: string) { Socket.instances.push(this); }
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = 3; }
}
const evidence: Record<string, unknown> = {};
let tree: any;
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  cacheClear();
  _resetAuthScopeForTests();
  Socket.instances = [];
  vi.stubGlobal('window', { setTimeout, clearTimeout, setInterval, clearInterval,
    location: { protocol: 'http:', host: 'audit' } });
  vi.stubGlobal('WebSocket', Socket);
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => 'blob:audit');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
});
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
  tree = null;
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
afterAll(() => writeFileSync('reports/audit_dcfc98dd/frontend_results.json', JSON.stringify(evidence, null, 2) + '\n'));

function deferredFetch() {
  const pending: any[] = [];
  vi.stubGlobal('fetch', vi.fn((url: string, opts: any) => new Promise((resolve, reject) => {
    const item = { url, signal: opts.signal, resolve: () => resolve({ status: 200, ok: true,
      headers: { get: () => 'audit-etag' }, blob: async () => new Blob(['jpeg']) }) };
    pending.push(item);
    opts.signal?.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')));
  })));
  return pending;
}

it('day enrichment aborts itself on its phase transition', async () => {
  let current: any;
  const calls: any[] = [];
  mocks.detections.mockImplementation((_cams, opts) => {
    calls.push(opts);
    if (opts.from === 100) return Promise.resolve({ by_camera: { Cam1: [] } });
    return new Promise((_resolve, reject) => opts.signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError'))));
  });
  function Harness() {
    current = useDetectionIndex({ cameras: ['Cam1'], date: '2020-01-01', runId: 1,
      priorityFromSec: 100, priorityToSec: 200, backgroundFromSec: 0, backgroundToSec: 86400, enabled: true });
    return null;
  }
  await act(async () => { tree = Renderer.create(React.createElement(Harness)); });
  const day = calls.find(x => x.from === 0);
  expect(day).toBeDefined();
  expect(day.signal.aborted).toBe(true);
  expect(current.backgroundLoading).toBe(true);
  evidence.day_enrichment = { request_count: calls.length, day_aborted: day.signal.aborted, loading_stuck: current.backgroundLoading };
});

it('notify for source 1 aborts the unfinished source 0 JPEG in the same run', async () => {
  const pending = deferredFetch();
  let current: any;
  function Harness() { current = useLiveGridPreviewWs(new Map([[7, [0, 1]]])); return null; }
  await act(async () => { tree = Renderer.create(React.createElement(Harness)); });
  const ws = Socket.instances[0];
  let first: any, second: any;
  await act(async () => {
    first = ws.onmessage({ data: JSON.stringify({ type: 'preview_notify', source_id: 0 }) });
    second = ws.onmessage({ data: JSON.stringify({ type: 'preview_notify', source_id: 1 }) });
  });
  expect(pending[0].signal.aborted).toBe(true);
  await act(async () => { pending[1].resolve(); await Promise.all([first, second]); });
  expect([...current.frames.keys()]).toEqual(['7:1']);
  evidence.cross_source_notify = { aborted_source_0: true, applied_keys: [...current.frames.keys()] };
});

it('late notify response restores a frame after auth scope clears it', async () => {
  const pending = deferredFetch();
  let current: any;
  function Harness() { current = useLiveGridPreviewWs(new Map([[7, [0]]])); return null; }
  await act(async () => { tree = Renderer.create(React.createElement(Harness)); });
  const ws = Socket.instances[0];
  let result: any;
  await act(async () => { result = ws.onmessage({ data: '{"type":"preview_notify","source_id":0}' }); });
  await act(async () => { bumpAuthScope('restricted'); });
  expect(pending[0].signal.aborted).toBe(false);
  await act(async () => { pending[0].resolve(); await result; });
  expect([...current.frames.keys()]).toEqual(['7:0']);
  evidence.auth_late_frame = { fetch_aborted_on_scope_change: false, restored_old_scope_frame: true };
});

it('metadata round robin restarts at zero and never visits source 15 under timeout load', async () => {
  const requested: number[] = [];
  mocks.request.mockImplementation((url, opts) => new Promise((_resolve, reject) => {
    requested.push(Number(url.split('source_id=')[1]));
    opts.signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError')));
  }));
  const store: any = new RunMetadataStore(7);
  store.listenersBySource = new Map(Array.from({ length: 16 }, (_, i) => [i, new Set([() => {}])]));
  store.startRestFallback();
  await vi.advanceTimersByTimeAsync(18001);
  const cursor = store.restCursor;
  store.stopRestFallback();
  store.close();
  expect(cursor).toBe(0);
  expect(requested).not.toContain(15);
  expect(requested.filter(x => x === 0).length).toBeGreaterThan(1);
  evidence.metadata_fairness = { requested_sources: requested, cursor, source_15_visited: false };
});

it('metadata store republishes previous user data after auth bump and remount', async () => {
  const store = new RunMetadataStore(7);
  const unsubscribe = store.subscribe(0, () => {});
  store.pushPayloadForTest({ source_id: 0, timestamp: Date.now() / 1000,
    objects: [{ object_id: 12345 }] } as any);
  unsubscribe();
  bumpAuthScope('restricted');
  const received: any[] = [];
  const secondUnsubscribe = store.subscribe(0, x => received.push(x));
  secondUnsubscribe();
  expect(received[0].objects[0].object_id).toBe(12345);
  evidence.metadata_auth_scope = { old_object_delivered_to_new_subscription: 12345 };
});

it('journal keeps existing rows when ACL epoch changes without changing filters', async () => {
  mocks.grouped.mockResolvedValue({ available: true, items: [{ row_key: 'old-Cam1' }] });
  let current: any;
  function Harness() { current = useJournalFeed('events', { date: '2020-01-01' }); return null; }
  await act(async () => { tree = Renderer.create(React.createElement(Harness)); });
  expect(current.rows.length).toBe(1);
  await act(async () => { bumpAuthScope('restricted'); tree.update(React.createElement(Harness)); });
  expect(current.rows[0].row_key).toBe('old-Cam1');
  evidence.journal_auth_scope = { old_rows_remain: true, requests: mocks.grouped.mock.calls.length };
});
