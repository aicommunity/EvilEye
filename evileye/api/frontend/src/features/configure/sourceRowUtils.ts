export type PixelRect = [number, number, number, number];

export type NormalizedSourceRegions = {
  split: boolean;
  num_split: number;
  source_ids: number[];
  source_names: string[];
  src_coords: PixelRect[] | [0];
};

export function cloneSourceRow(row: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(row)) as Record<string, unknown>;
}

export function parseSourceRegions(row: Record<string, unknown>): {
  split: boolean;
  ids: number[];
  names: string[];
  coords: PixelRect[];
} {
  const idsRaw = row.source_ids;
  const namesRaw = row.source_names;
  let ids: number[] = [];
  if (Array.isArray(idsRaw)) {
    ids = idsRaw.map((x) => Number(x)).filter((n) => !Number.isNaN(n));
  } else if (row.source_id != null && !Number.isNaN(Number(row.source_id))) {
    ids = [Number(row.source_id)];
  }
  if (!ids.length) ids = [0];

  let names: string[] = [];
  if (Array.isArray(namesRaw)) {
    names = namesRaw.map((x) => String(x));
  }
  while (names.length < ids.length) {
    names.push(`Cam${ids[names.length] + 1}`);
  }
  names = names.slice(0, Math.max(ids.length, names.length));

  const coordsRaw = row.src_coords;
  const coords: PixelRect[] = [];
  if (Array.isArray(coordsRaw)) {
    for (const item of coordsRaw) {
      if (!Array.isArray(item) || item.length !== 4) continue;
      const rect: PixelRect = [
        Math.round(Number(item[0])),
        Math.round(Number(item[1])),
        Math.max(1, Math.round(Number(item[2]))),
        Math.max(1, Math.round(Number(item[3]))),
      ];
      if (rect.every((n) => !Number.isNaN(n))) coords.push(rect);
    }
  }

  // Trust explicit split flag only — do not force-on from ids.length.
  const split = Boolean(row.split);
  return { split, ids, names: names.slice(0, ids.length), coords };
}

export function canvasSizeFromCoords(coords: PixelRect[], fallbackW = 1920, fallbackH = 1080): { w: number; h: number } {
  if (!coords.length) return { w: fallbackW, h: fallbackH };
  let w = 0;
  let h = 0;
  for (const [x, y, rw, rh] of coords) {
    w = Math.max(w, x + rw);
    h = Math.max(h, y + rh);
  }
  return { w: Math.max(w, 1), h: Math.max(h, 1) };
}

/** Collect all logical source_ids used by pipeline source rows. */
export function collectOccupiedSourceIds(
  sources: Record<string, unknown>[],
  exceptIndex?: number,
): Set<number> {
  const occupied = new Set<number>();
  sources.forEach((row, i) => {
    if (exceptIndex != null && i === exceptIndex) return;
    const ids = row.source_ids;
    if (Array.isArray(ids)) {
      for (const x of ids) {
        const n = Number(x);
        if (!Number.isNaN(n)) occupied.add(n);
      }
    } else if (row.source_id != null && !Number.isNaN(Number(row.source_id))) {
      occupied.add(Number(row.source_id));
    }
  });
  return occupied;
}

function nextFreeId(occupied: Set<number>, from = 0): number {
  let id = Math.max(0, from);
  while (occupied.has(id)) id += 1;
  return id;
}

export function padRegions(
  num: number,
  ids: number[],
  names: string[],
  coords: PixelRect[],
  frameW = 1920,
  frameH = 1080,
  occupiedIds?: Iterable<number>,
): { ids: number[]; names: string[]; coords: PixelRect[] } {
  const n = Math.max(1, Math.floor(num));
  const blocked = new Set<number>(occupiedIds ?? []);
  const nextIds = ids.slice(0, n);
  const nextNames = names.slice(0, n);
  const nextCoords = coords.slice(0, n);
  const stripH = Math.max(1, Math.floor(frameH / n));

  // Resolve duplicates within the row (keep first).
  for (let i = 0; i < nextIds.length; i++) {
    const first = nextIds.indexOf(nextIds[i]);
    if (first !== i) {
      const id = nextFreeId(blocked, nextIds[i] + 1);
      nextIds[i] = id;
      nextNames[i] = `Cam${id + 1}`;
    }
    blocked.add(nextIds[i]);
  }

  while (nextIds.length < n) {
    const id = nextFreeId(blocked, 0);
    blocked.add(id);
    nextIds.push(id);
  }
  while (nextNames.length < n) {
    nextNames.push(`Cam${nextIds[nextNames.length] + 1}`);
  }
  while (nextCoords.length < n) {
    const i = nextCoords.length;
    nextCoords.push([0, i * stripH, frameW, i === n - 1 ? frameH - i * stripH : stripH]);
  }
  return {
    ids: nextIds,
    names: nextNames.slice(0, n),
    coords: nextCoords.slice(0, n),
  };
}

export function applyRegionsToRow(
  row: Record<string, unknown>,
  regions: { split: boolean; ids: number[]; names: string[]; coords: PixelRect[] },
): Record<string, unknown> {
  const next = { ...row };
  if (!regions.split || regions.ids.length <= 1) {
    const id = regions.ids[0] ?? 0;
    const name = regions.names[0] ?? `Cam${id + 1}`;
    next.split = false;
    next.num_split = 0;
    next.source_ids = [id];
    next.source_names = [name];
    next.src_coords = [0];
    return next;
  }
  const n = regions.ids.length;
  next.split = true;
  next.num_split = n;
  next.source_ids = [...regions.ids];
  next.source_names = [...regions.names].slice(0, n);
  next.src_coords = regions.coords.slice(0, n).map((c) => [...c] as PixelRect);
  return next;
}

export function validateSplitRegions(regions: {
  split: boolean;
  ids: number[];
  names: string[];
  coords: PixelRect[];
}): string | null {
  if (!regions.split) return null;
  if (regions.ids.length < 2) return 'need_regions';
  if (regions.ids.length !== regions.names.length || regions.ids.length !== regions.coords.length) {
    return 'length_mismatch';
  }
  const seen = new Set<number>();
  for (const id of regions.ids) {
    if (seen.has(id)) return 'duplicate_id';
    seen.add(id);
  }
  for (const [, , w, h] of regions.coords) {
    if (w <= 0 || h <= 0) return 'bad_rect';
  }
  return null;
}

export function findSourceRowIndex(
  sources: Record<string, unknown>[],
  basicId: number,
  fallbackIndex: number,
): number {
  for (let i = 0; i < sources.length; i++) {
    const ids = sources[i].source_ids;
    if (Array.isArray(ids) && Number(ids[0]) === basicId) return i;
  }
  if (fallbackIndex >= 0 && fallbackIndex < sources.length) return fallbackIndex;
  return -1;
}

export function displaySourceName(row: Record<string, unknown>): string {
  const names = row.source_names;
  if (Array.isArray(names) && names.length) {
    const parts = names.map((x) => String(x || '').trim()).filter(Boolean);
    if (parts.length > 1) return parts.join('+');
    if (parts[0]) return parts[0];
  }
  if (typeof row.camera === 'string' && row.camera && !row.camera.includes('://')) return row.camera;
  return 'Cam';
}
