import type { StreamMetadataObject } from '../../api';

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

