import { describe, expect, it } from 'vitest';
import {
  cameraTileActive,
  shouldRaisePreviewError,
  wantLiveSnapshotPoll,
  wantLiveWsPreview,
} from './livePreviewPrefer';

describe('wantLiveSnapshotPoll / wantLiveWsPreview (A1)', () => {
  it('keeps snapshot while WS connected but no blob yet', () => {
    const base = { running: true, active: true, useMjpeg: false, previewWsActive: true, hasWsFrame: false };
    expect(wantLiveSnapshotPoll(base)).toBe(true);
    expect(wantLiveWsPreview(base)).toBe(false);
  });

  it('switches to WS blob when frame arrives', () => {
    const base = { running: true, active: true, useMjpeg: false, previewWsActive: true, hasWsFrame: true };
    expect(wantLiveSnapshotPoll(base)).toBe(false);
    expect(wantLiveWsPreview(base)).toBe(true);
  });

  it('disables both when tile inactive', () => {
    const base = { running: true, active: false, useMjpeg: false, previewWsActive: true, hasWsFrame: false };
    expect(wantLiveSnapshotPoll(base)).toBe(false);
    expect(wantLiveWsPreview(base)).toBe(false);
  });
});

describe('cameraTileActive (A2)', () => {
  it('treats all tiles active before first IO callback in fixed mode', () => {
    expect(cameraTileActive({ mode: 'fixed', ioReady: false, visible: false, selected: false })).toBe(true);
  });

  it('after IO only visible or selected stay active', () => {
    expect(cameraTileActive({ mode: 'fixed', ioReady: true, visible: false, selected: false })).toBe(false);
    expect(cameraTileActive({ mode: 'fixed', ioReady: true, visible: true, selected: false })).toBe(true);
    expect(cameraTileActive({ mode: 'fixed', ioReady: true, visible: false, selected: true })).toBe(true);
  });

  it('fit mode always active', () => {
    expect(cameraTileActive({ mode: 'fit', ioReady: true, visible: false, selected: false })).toBe(true);
  });
});

describe('shouldRaisePreviewError', () => {
  it('suppresses error while WS blob is healthy', () => {
    expect(shouldRaisePreviewError({ previewWsActive: true, hasWsFrame: true })).toBe(false);
  });

  it('raises when WS inactive or no frame', () => {
    expect(shouldRaisePreviewError({ previewWsActive: false, hasWsFrame: true })).toBe(true);
    expect(shouldRaisePreviewError({ previewWsActive: true, hasWsFrame: false })).toBe(true);
  });
});
