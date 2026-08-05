export type LayoutMode = 'fit' | 'fixed';

/** Columns for fit mode. Live: no max clamp. Playback: pass maxCols=4. */
export function fitColsForCount(n: number, maxCols?: number): number {
  if (n <= 0) return 1;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
  return maxCols != null ? Math.min(maxCols, cols) : cols;
}
