import { useEffect, useState } from 'react';

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
    const rawV2 = localStorage.getItem(KEY_V2);
    if (rawV2) {
      const parsed = JSON.parse(rawV2) as Partial<PlaybackLayoutState>;
      return {
        mode: parsed.mode === 'fixed' ? 'fixed' : 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds : [],
        order: Array.isArray(parsed.order) ? parsed.order : [],
      };
    }
    const rawV1 = localStorage.getItem(KEY_V1);
    if (rawV1) {
      const parsed = JSON.parse(rawV1) as Partial<PlaybackLayoutState>;
      return {
        mode: 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds : [],
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
    localStorage.setItem(KEY_V2, JSON.stringify({ mode, cols, selectedIds, order }));
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
