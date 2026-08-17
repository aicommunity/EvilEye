import type { CSSProperties } from 'react';
import type { StreamMetadata } from '../../api';

export type OverlayLayoutBox = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export function OverlayCanvas({
  meta,
  layoutBox,
}: {
  meta: StreamMetadata | null;
  layoutBox?: OverlayLayoutBox;
}) {
  if (!meta?.objects?.length && !meta?.zones?.length) return null;

  const style: CSSProperties = layoutBox
    ? {
        position: 'absolute',
        left: layoutBox.left,
        top: layoutBox.top,
        width: layoutBox.width || '100%',
        height: layoutBox.height || '100%',
        pointerEvents: 'none',
      }
    : {
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      };

  return (
    <svg className="journal-preview-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" style={style}>
      {(meta.zones ?? []).map((z, i) => {
        if (!z.points?.length) return null;
        const points = z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ');
        return (
          <polygon
            key={`z${i}`}
            points={points}
            fill="rgba(59,130,246,0.15)"
            stroke="#3b82f6"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
      {(meta.objects ?? []).map((o, i) => {
        const b = o.bbox;
        if (!b || b.length !== 4) return null;
        const [x1, y1, x2, y2] = b;
        return (
          <rect
            key={`o${i}`}
            x={x1 * 100}
            y={y1 * 100}
            width={(x2 - x1) * 100}
            height={(y2 - y1) * 100}
            fill="none"
            stroke="#22c55e"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
    </svg>
  );
}
