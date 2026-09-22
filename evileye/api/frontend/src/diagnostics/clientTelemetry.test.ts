import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('clientTelemetry flushNow', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal('console', { ...console, debug: vi.fn(), warn: vi.fn() });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('re-queues batch when upload returns HTTP 403', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 403 });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('window', {
      setInterval: vi.fn(() => 1),
      clearInterval: vi.fn(),
      addEventListener: vi.fn(),
      innerWidth: 800,
      innerHeight: 600,
    });
    vi.stubGlobal('document', { addEventListener: vi.fn(), visibilityState: 'visible' });
    vi.stubGlobal('sessionStorage', {
      getItem: () => null,
      setItem: vi.fn(),
    });
    vi.stubGlobal('localStorage', { getItem: () => null });
    vi.stubGlobal('navigator', { userAgent: 'vitest', sendBeacon: vi.fn() });

    const mod = await import('./clientTelemetry');
    mod.setClientTelemetryEnabled(true, { autoUpload: true });
    mod.clientTelemetryLog('ping', {}, 'other');
    const before = mod.isClientTelemetryEnabled();
    expect(before).toBe(true);

    // Force pending via internal API: log already queued; flush manually.
    await mod.flushNow();
    expect(fetchMock).toHaveBeenCalled();
    const snap = (window as unknown as { __evileyeDebug: { snapshot: () => { pendingUpload: number; counters: Record<string, number> } } })
      .__evileyeDebug.snapshot();
    expect(snap.counters.upload_http_error).toBeGreaterThanOrEqual(1);
    expect(snap.pendingUpload).toBeGreaterThanOrEqual(1);
  });

  it('clears pending on HTTP 200', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('window', {
      setInterval: vi.fn(() => 1),
      clearInterval: vi.fn(),
      addEventListener: vi.fn(),
      innerWidth: 800,
      innerHeight: 600,
    });
    vi.stubGlobal('document', { addEventListener: vi.fn(), visibilityState: 'visible' });
    vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: vi.fn() });
    vi.stubGlobal('localStorage', { getItem: () => null });
    vi.stubGlobal('navigator', { userAgent: 'vitest', sendBeacon: vi.fn() });

    const mod = await import('./clientTelemetry');
    mod.setClientTelemetryEnabled(true, { autoUpload: true });
    mod.clientTelemetryLog('ping', {}, 'other');
    await mod.flushNow();
    const snap = (window as unknown as { __evileyeDebug: { snapshot: () => { pendingUpload: number; counters: Record<string, number> } } })
      .__evileyeDebug.snapshot();
    expect(snap.counters.upload_ok).toBeGreaterThanOrEqual(1);
    expect(snap.pendingUpload).toBe(0);
  });
});
