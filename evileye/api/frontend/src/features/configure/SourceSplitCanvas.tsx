import { useRef, useState } from 'react';
import type { PixelRect } from './sourceRowUtils';

export function SourceSplitCanvas({
  width,
  height,
  coords,
  selected,
  readOnly,
  onSelect,
  onReplaceRect,
  bgUrl,
}: {
  width: number;
  height: number;
  coords: PixelRect[];
  selected: number | null;
  readOnly: boolean;
  onSelect: (index: number | null) => void;
  onReplaceRect: (index: number | null, rect: PixelRect) => void;
  bgUrl?: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [drawing, setDrawing] = useState<PixelRect | null>(null);

  const toPx = (e: React.MouseEvent): [number, number] => {
    const rect = wrapRef.current!.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    const y = ((e.clientY - rect.top) / rect.height) * height;
    return [Math.max(0, Math.min(width, x)), Math.max(0, Math.min(height, y))];
  };

  return (
    <div
      ref={wrapRef}
      className="source-split-canvas"
      style={{
        aspectRatio: `${Math.max(width, 1)} / ${Math.max(height, 1)}`,
        backgroundImage: bgUrl ? `url(${bgUrl})` : undefined,
      }}
      onMouseDown={(e) => {
        if (readOnly) return;
        const [x, y] = toPx(e);
        setDrawing([x, y, 1, 1]);
        onSelect(null);
      }}
      onMouseMove={(e) => {
        if (!drawing) return;
        const [x, y] = toPx(e);
        const x0 = drawing[0];
        const y0 = drawing[1];
        setDrawing([
          Math.min(x0, x),
          Math.min(y0, y),
          Math.max(1, Math.abs(x - x0)),
          Math.max(1, Math.abs(y - y0)),
        ]);
      }}
      onMouseUp={() => {
        if (!drawing) return;
        if (selected != null && selected >= 0 && selected < coords.length) {
          onReplaceRect(selected, drawing);
        } else {
          onReplaceRect(null, drawing);
        }
        setDrawing(null);
      }}
      onMouseLeave={() => {
        if (drawing) {
          if (selected != null && selected >= 0 && selected < coords.length) {
            onReplaceRect(selected, drawing);
          } else {
            onReplaceRect(null, drawing);
          }
          setDrawing(null);
        }
      }}
    >
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="source-split-svg">
        {[...coords, ...(drawing ? [drawing] : [])].map((r, i) => {
          const isDraw = drawing != null && i === coords.length;
          const active = !isDraw && selected === i;
          return (
            <rect
              key={isDraw ? 'draw' : i}
              x={r[0]}
              y={r[1]}
              width={r[2]}
              height={r[3]}
              className={active ? 'source-split-rect active' : 'source-split-rect'}
              onClick={(ev) => {
                ev.stopPropagation();
                if (!isDraw) onSelect(i);
              }}
            />
          );
        })}
        {coords.map((r, i) => (
          <text key={`t-${i}`} x={r[0] + 8} y={r[1] + 20} className="source-split-label">
            #{i}
          </text>
        ))}
      </svg>
    </div>
  );
}
