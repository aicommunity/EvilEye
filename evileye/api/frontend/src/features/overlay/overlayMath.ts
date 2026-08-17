import type { StreamMetadataObject, StreamMetadata } from '../../api';

export function formatObjectLabel(o: StreamMetadataObject): string {
  const classLabel = o.class_name ?? (o.class_id != null ? `class_${o.class_id}` : 'object');
  const trackLabel = o.track_id != null ? String(o.track_id) : '?';
  const confLabel = o.conf != null ? Number(o.conf).toFixed(2) : '?';
  const prefix = o.global_id != null ? `G${o.global_id} ` : '';
  return `${prefix}${classLabel} [${trackLabel}:${confLabel}]`;
}

export function polygonCentroid(points: Array<[number, number]>): [number, number] {
  if (!points.length) return [0, 0];
  let x = 0;
  let y = 0;
  for (const [px, py] of points) {
    x += px;
    y += py;
  }
  return [x / points.length, y / points.length];
}

export function rgbArrayToCss(color?: [number, number, number] | null, fallback = '#ef4444'): string {
  if (!color || color.length !== 3) return fallback;
  const [r, g, b] = color.map((v) => Math.max(0, Math.min(255, Number(v) || 0)));
  return `rgb(${r}, ${g}, ${b})`;
}

function transformPoint(
  x: number,
  y: number,
  cropLeft: number,
  cropTop: number,
  cropW: number,
  cropH: number,
): [number, number] | null {
  if (cropW <= 0 || cropH <= 0) return null;
  const nx = (x - cropLeft) / cropW;
  const ny = (y - cropTop) / cropH;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return [nx, ny];
}

function transformBbox(
  bbox: [number, number, number, number],
  cropLeft: number,
  cropTop: number,
  cropW: number,
  cropH: number,
): [number, number, number, number] | null {
  const [x1, y1, x2, y2] = bbox;
  const p1 = transformPoint(x1, y1, cropLeft, cropTop, cropW, cropH);
  const p2 = transformPoint(x2, y2, cropLeft, cropTop, cropW, cropH);
  if (!p1 || !p2) return null;
  const nx1 = Math.min(p1[0], p2[0]);
  const ny1 = Math.min(p1[1], p2[1]);
  const nx2 = Math.max(p1[0], p2[0]);
  const ny2 = Math.max(p1[1], p2[1]);
  if (nx2 <= 0 || ny2 <= 0 || nx1 >= 1 || ny1 >= 1) return null;
  return [
    Math.max(0, nx1),
    Math.max(0, ny1),
    Math.min(1, nx2),
    Math.min(1, ny2),
  ];
}

/** Re-map normalized coords when backend reference size differs from actual video. */
export function rescaleMetadataForVideoSize(
  meta: StreamMetadata | null,
  videoW: number,
  videoH: number,
): StreamMetadata | null {
  if (!meta || videoW <= 0 || videoH <= 0) return meta;
  const ref = meta.coord_ref;
  if (!ref || ref.w <= 0 || ref.h <= 0) return meta;
  if (ref.w === videoW && ref.h === videoH) return meta;

  const sx = ref.w / videoW;
  const sy = ref.h / videoH;
  const scaleX = (v: number) => v * sx;
  const scaleY = (v: number) => v * sy;

  const objects = (meta.objects ?? []).map((obj) => {
    const next = { ...obj };
    if (obj.bbox?.length === 4) {
      const [x1, y1, x2, y2] = obj.bbox;
      next.bbox = [scaleX(x1), scaleY(y1), scaleX(x2), scaleY(y2)];
    }
    if (obj.trail?.length) {
      next.trail = obj.trail.map(([x, y]) => [scaleX(x), scaleY(y)] as [number, number]);
    }
    return next;
  });

  const debug_rois = (meta.debug_rois ?? []).map((roi) => {
    const [x1, y1, x2, y2] = roi;
    return [scaleX(x1), scaleY(y1), scaleX(x2), scaleY(y2)] as [number, number, number, number];
  });

  return {
    ...meta,
    coord_ref: { w: videoW, h: videoH },
    objects,
    debug_rois,
  };
}

/** Map normalized overlay coords from parent frame into split-crop space. */
export function transformMetadataForCrop(
  meta: StreamMetadata | null,
  srcCoords: [number, number, number, number],
  parentW: number,
  parentH: number,
): StreamMetadata | null {
  if (!meta || parentW <= 0 || parentH <= 0) return meta;
  const [sx, sy, sw, sh] = srcCoords;
  const cropLeft = sx / parentW;
  const cropTop = sy / parentH;
  const cropW = sw / parentW;
  const cropH = sh / parentH;

  const objects = (meta.objects ?? [])
    .map((obj) => {
      if (!obj.bbox) return null;
      const bbox = transformBbox(obj.bbox, cropLeft, cropTop, cropW, cropH);
      if (!bbox) return null;
      const trail = (obj.trail ?? [])
        .map(([x, y]) => transformPoint(x, y, cropLeft, cropTop, cropW, cropH))
        .filter((p): p is [number, number] => p != null);
      return { ...obj, bbox, trail };
    })
    .filter((o): o is NonNullable<typeof o> => o != null);

  const zones = (meta.zones ?? [])
    .map((zone) => {
      const points = (zone.points ?? [])
        .map(([x, y]) => transformPoint(x, y, cropLeft, cropTop, cropW, cropH))
        .filter((p): p is [number, number] => p != null);
      if (points.length < 2) return null;
      return { ...zone, points };
    })
    .filter((z): z is NonNullable<typeof z> => z != null);

  const debug_rois = (meta.debug_rois ?? [])
    .map((roi) => transformBbox(roi, cropLeft, cropTop, cropW, cropH))
    .filter((r): r is [number, number, number, number] => r != null);

  return {
    ...meta,
    objects,
    zones,
    debug_rois,
  };
}
