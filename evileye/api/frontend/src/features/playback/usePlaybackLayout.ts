import { useEffect, useState } from 'react';

const KEY_V3 = 'evileye.playback.layout.v3';
const KEY_V2 = 'evileye.playback.layout.v2';
const KEY_V1 = 'evileye.playback.layout.v1';

export type LayoutMode = 'fit' | 'fixed';

interface PlaybackLayoutState {
  mode: LayoutMode;
  cols: number;
  selectedIds: string[];
  order: string[];
}

function load(): PlaybackLayoutState {
  try {
    const rawV3 = localStorage.getItem(KEY_V3);
    if (rawV3) {
      const parsed = JSON.parse(rawV3) as Partial<PlaybackLayoutState>;
      return {
        mode: parsed.mode === 'fixed' ? 'fixed' : 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds : [],
        order: Array.isArray(parsed.order) ? parsed.order : [],
      };
    }
    // Migrate v1/v2: keep mode/cols/order, drop selectedIds so all cams are selected by default.
    const rawLegacy = localStorage.getItem(KEY_V2) || localStorage.getItem(KEY_V1);
    if (rawLegacy) {
      const parsed = JSON.parse(rawLegacy) as Partial<PlaybackLayoutState>;
      return {
        mode: parsed.mode === 'fixed' ? 'fixed' : 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        selectedIds: [],
        order: Array.isArray(parsed.order) ? parsed.order : [],
      };
    }
  } catch {
    /* ignore */
  }
  return { mode: 'fit', cols: 2, selectedIds: [], order: [] };
}

export function usePlaybackLayout() {
  const initial = load();
  const [mode, setModeState] = useState<LayoutMode>(initial.mode);
  const [cols, setColsState] = useState(initial.cols);
  const [selectedIds, setSelectedIdsState] = useState<string[]>(initial.selectedIds);
  const [order, setOrderState] = useState<string[]>(initial.order);

  useEffect(() => {
    localStorage.setItem(KEY_V3, JSON.stringify({ mode, cols, selectedIds, order }));
  }, [mode, cols, selectedIds, order]);

  return {
    mode,
    setMode: setModeState,
    cols,
    setCols: setColsState,
    selectedIds,
    setSelectedIds: setSelectedIdsState,
    order,
    setOrder: setOrderState,
  };
}
