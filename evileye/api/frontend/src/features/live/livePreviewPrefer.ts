/** Pure helpers for Live preview source selection (A1). */

export function wantLiveSnapshotPoll(opts: {
  running: boolean;
  active: boolean;
  useMjpeg: boolean;
  previewWsActive: boolean;
  hasWsFrame: boolean;
}): boolean {
  const { running, active, useMjpeg, previewWsActive, hasWsFrame } = opts;
  return running && active && !useMjpeg && !(previewWsActive && hasWsFrame);
}

export function wantLiveWsPreview(opts: {
  running: boolean;
  active: boolean;
  useMjpeg: boolean;
  previewWsActive: boolean;
  hasWsFrame: boolean;
}): boolean {
  const { running, active, useMjpeg, previewWsActive, hasWsFrame } = opts;
  return running && active && !useMjpeg && previewWsActive && hasWsFrame;
}

/** Fixed-grid cold start: active until first IntersectionObserver callback (A2). */
export function cameraTileActive(opts: {
  mode: 'fit' | 'fixed';
  ioReady: boolean;
  visible: boolean;
  selected: boolean;
}): boolean {
  return opts.mode === 'fit' || !opts.ioReady || opts.visible || opts.selected;
}
