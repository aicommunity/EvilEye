import { describe, expect, it } from 'vitest';
import type { StateCamera } from '../../api';
import { effectiveFrameAgeSec, resolvePreviewMode } from './liveHealth';

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
  it('marks stale when effective age exceeds threshold', () => {
    const mode = resolvePreviewMode(cam({ last_frame_age_sec: 4.5 }), false, {
      camerasPolledAtMs: Date.now() - 2000,
    });
    expect(mode).toBe('stale');
  });

  it('stays live when WS preview is fresh even if API age is stale', () => {
    const mode = resolvePreviewMode(
      cam({ last_frame_age_sec: 12, preview_available: true, is_working: true }),
      false,
      { previewFrameAgeSec: 0.5, camerasPolledAtMs: Date.now() - 10_000 },
    );
    expect(mode).toBe('live');
  });

  it('ignores preview_available false when WS preview is fresh', () => {
    const mode = resolvePreviewMode(
      cam({ last_frame_age_sec: 12, preview_available: false, is_working: true }),
      false,
      { previewFrameAgeSec: 0.5, camerasPolledAtMs: Date.now() - 10_000 },
    );
    expect(mode).toBe('live');
  });
});
