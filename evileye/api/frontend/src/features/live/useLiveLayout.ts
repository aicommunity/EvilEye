import { useEffect, useState } from 'react';

const KEY_V2 = 'evileye.live.layout.v2';
const KEY_V1 = 'evileye.live.layout.v1';

export type LayoutMode = 'fit' | 'fixed';

interface LayoutState {
  mode: LayoutMode;
  cols: number;
  order: string[];
}

function load(): LayoutState {
  try {
    const rawV2 = localStorage.getItem(KEY_V2);
    if (rawV2) {
      const parsed = JSON.parse(rawV2) as Partial<LayoutState>;
      return {
        mode: parsed.mode === 'fixed' ? 'fixed' : 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        order: Array.isArray(parsed.order) ? parsed.order : [],
      };
    }
    const rawV1 = localStorage.getItem(KEY_V1);
    if (rawV1) {
      const parsed = JSON.parse(rawV1) as Partial<LayoutState>;
      return {
        mode: 'fit',
        cols: Math.max(1, Math.min(4, parsed.cols || 2)),
        order: Array.isArray(parsed.order) ? parsed.order : [],
      };
    }
  } catch {
    /* ignore */
  }
  return { mode: 'fit', cols: 2, order: [] };
}

export function useLiveLayout() {
  const initial = load();
  const [mode, setModeState] = useState<LayoutMode>(initial.mode);
  const [cols, setColsState] = useState(initial.cols);
  const [order, setOrderState] = useState<string[]>(initial.order);

  useEffect(() => {
    localStorage.setItem(KEY_V2, JSON.stringify({ mode, cols, order }));
  }, [mode, cols, order]);

  return {
    mode,
    setMode: setModeState,
    cols,
    setCols: setColsState,
    order,
    setOrder: setOrderState,
  };
}
