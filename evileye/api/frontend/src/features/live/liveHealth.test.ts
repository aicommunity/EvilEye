import { describe, expect, it } from 'vitest';
import type { StateCamera } from '../../api';
import {
  effectiveFrameAgeSec,
  LIVE_STALE_ENTER_SEC,
  LIVE_STALE_EXIT_SEC,
  resolvePreviewMode,
} from './liveHealth';

function cam(partial: Partial<StateCamera> = {}): StateCamera {
  return {
    run_id: 1,
    source_id: 0,
    source_name: 'Cam0',
    run_state: 'running',
    preview_available: true,
    is_working: true,
    ...partial,
  } as StateCamera;
}

describe('effectiveFrameAgeSec', () => {
  it('ages API snapshot between polls', () => {
    const polledAt = Date.now() - 3000;
    const age = effectiveFrameAgeSec(cam({ last_frame_age_sec: 2 }), {
      camerasPolledAtMs: polledAt,
    });
    expect(age).toBeCloseTo(5, 0);
  });

  it('prefers fresher WS preview age', () => {
    const age = effectiveFrameAgeSec(cam({ last_frame_age_sec: 8 }), {
      previewFrameAgeSec: 0.4,
      camerasPolledAtMs: Date.now(),
    });
    expect(age).toBeCloseTo(0.4, 5);
  });
});

describe('resolvePreviewMode', () => {
  it('stays live when age is between exit and enter thresholds', () => {
    // age ≈ 6.5 — above EXIT but below ENTER
    const mode = resolvePreviewMode(cam({ last_frame_age_sec: 4.5 }), false, {
      camerasPolledAtMs: Date.now() - 2000,
    });
    expect(mode).toBe('live');
  });

  it('marks stale when effective age exceeds enter threshold', () => {
    const mode = resolvePreviewMode(cam({ last_frame_age_sec: LIVE_STALE_ENTER_SEC }), false, {
      camerasPolledAtMs: Date.now() - 2000,
    });
    expect(mode).toBe('stale');
  });

  it('uses hysteresis: stays stale until age drops below exit', () => {
    const stillStale = resolvePreviewMode(cam({ last_frame_age_sec: LIVE_STALE_EXIT_SEC }), false, {
      camerasPolledAtMs: Date.now(),
      previousMode: 'stale',
    });
    expect(stillStale).toBe('stale');

    const recovered = resolvePreviewMode(cam({ last_frame_age_sec: LIVE_STALE_EXIT_SEC - 0.5 }), false, {
      camerasPolledAtMs: Date.now(),
      previousMode: 'stale',
    });
    expect(recovered).toBe('live');
  });

  it('stays live when WS preview is fresh even if API age is stale', () => {
    const mode = resolvePreviewMode(
      cam({ last_frame_age_sec: 20, preview_available: true, is_working: true }),
      false,
      { previewFrameAgeSec: 0.5, camerasPolledAtMs: Date.now() - 10_000 },
    );
    expect(mode).toBe('live');
  });

  it('ignores preview_available false when WS preview is fresh', () => {
    const mode = resolvePreviewMode(
      cam({ last_frame_age_sec: 20, preview_available: false, is_working: true }),
      false,
      { previewFrameAgeSec: 0.5, camerasPolledAtMs: Date.now() - 10_000 },
    );
    expect(mode).toBe('live');
  });
});
