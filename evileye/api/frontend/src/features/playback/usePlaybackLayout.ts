import { useEffect, useState } from 'react';

const KEY = 'evileye.playback.layout.v1';

interface PlaybackLayoutState {
  cols: number;
  selectedIds: string[];
  order: string[];
}

function load(): PlaybackLayoutState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { cols: 2, selectedIds: [], order: [] };
    const parsed = JSON.parse(raw) as PlaybackLayoutState;
    return {
      cols: Math.max(1, Math.min(4, parsed.cols || 2)),
      selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds : [],
      order: Array.isArray(parsed.order) ? parsed.order : [],
    };
  } catch {
    return { cols: 2, selectedIds: [], order: [] };
  }
}

export function usePlaybackLayout() {
  const [cols, setColsState] = useState(() => load().cols);
  const [selectedIds, setSelectedIdsState] = useState<string[]>(() => load().selectedIds);
  const [order, setOrderState] = useState<string[]>(() => load().order);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify({ cols, selectedIds, order }));
  }, [cols, selectedIds, order]);

  return {
    cols,
    setCols: setColsState,
    selectedIds,
    setSelectedIds: setSelectedIdsState,
    order,
    setOrder: setOrderState,
  };
}
