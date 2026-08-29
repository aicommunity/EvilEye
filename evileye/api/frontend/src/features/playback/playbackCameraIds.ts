/**
 * Composite stream folders are named like `Cam2-Cam3` (joined source_names).
 * Timeline/segments APIs should use logical ids (`Cam2`, `Cam3`) only.
 */
export function isCompositeCameraId(id: string): boolean {
  return id.includes('-');
}

/** Drop composite folder ids; keep logical camera ids. */
export function filterLogicalCameraIds(ids: string[]): string[] {
  return ids.filter((id) => id && !isCompositeCameraId(id));
}

/** Prefer logical cameras when both composite folders and parts appear in a list. */
export function preferLogicalCameras<T extends { id: string }>(cameras: T[]): T[] {
  return cameras.filter((c) => !isCompositeCameraId(c.id));
}
