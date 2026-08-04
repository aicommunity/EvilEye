import { useEffect, useState } from 'react';

const KEY = 'evileye.live.layout.v1';

interface LayoutState {
  cols: number;
  order: string[];
}

function load(): LayoutState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { cols: 2, order: [] };
    const parsed = JSON.parse(raw) as LayoutState;
    return {
      cols: Math.max(1, Math.min(4, parsed.cols || 2)),
      order: Array.isArray(parsed.order) ? parsed.order : [],
    };
  } catch {
    return { cols: 2, order: [] };
  }
}

export function useLiveLayout() {
  const [cols, setColsState] = useState(() => load().cols);
  const [order, setOrderState] = useState<string[]>(() => load().order);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify({ cols, order }));
  }, [cols, order]);

  return {
    cols,
    setCols: setColsState,
    order,
    setOrder: setOrderState,
  };
}
