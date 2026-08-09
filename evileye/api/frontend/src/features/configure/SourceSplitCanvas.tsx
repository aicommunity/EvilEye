import { useCallback, useRef, useState } from 'react';
import type { PixelRect } from './sourceRowUtils';

type DragMode =
  | { kind: 'move'; index: number; startX: number; startY: number; orig: PixelRect }
  | {
      kind: 'resize';
      index: number;
      edge: 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
      startX: number;
      startY: number;
      orig: PixelRect;
    };

const HANDLE = 10; // hit size in screen px, converted via viewBox

function hitTest(coords: PixelRect[], x: number, y: number): number | null {
  for (let i = coords.length - 1; i >= 0; i--) {
    const [rx, ry, rw, rh] = coords[i];
    if (x >= rx && x <= rx + rw && y >= ry && y <= ry + rh) return i;
  }
  return null;
}

function edgeAt(
  rect: PixelRect,
  x: number,
  y: number,
  tol: number,
): 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw' | null {
  const [rx, ry, rw, rh] = rect;
  const nearL = Math.abs(x - rx) <= tol;
  const nearR = Math.abs(x - (rx + rw)) <= tol;
  const nearT = Math.abs(y - ry) <= tol;
  const nearB = Math.abs(y - (ry + rh)) <= tol;
  const inY = y >= ry - tol && y <= ry + rh + tol;
  const inX = x >= rx - tol && x <= rx + rw + tol;
  if (nearT && nearL) return 'nw';
  if (nearT && nearR) return 'ne';
  if (nearB && nearL) return 'sw';
  if (nearB && nearR) return 'se';
  if (nearT && inX) return 'n';
  if (nearB && inX) return 's';
  if (nearL && inY) return 'w';
  if (nearR && inY) return 'e';
  return null;
}

function applyResize(orig: PixelRect, edge: string, x: number, y: number, maxW: number, maxH: number): PixelRect {
  let [rx, ry, rw, rh] = orig;
  const right = rx + rw;
  const bottom = ry + rh;
  if (edge.includes('w')) rx = Math.min(Math.max(0, x), right - 1);
  if (edge.includes('e')) {
    const nr = Math.max(rx + 1, Math.min(maxW, x));
    rw = nr - rx;
  } else if (edge.includes('w')) {
    rw = right - rx;
  }
  if (edge.includes('n')) ry = Math.min(Math.max(0, y), bottom - 1);
  if (edge.includes('s')) {
    const nb = Math.max(ry + 1, Math.min(maxH, y));
    rh = nb - ry;
  } else if (edge.includes('n')) {
    rh = bottom - ry;
  }
  return [
    Math.max(0, Math.min(rx, maxW - 1)),
    Math.max(0, Math.min(ry, maxH - 1)),
    Math.max(1, Math.min(rw, maxW - rx)),
    Math.max(1, Math.min(rh, maxH - ry)),
  ];
}

export function SourceSplitCanvas({
  width,
  height,
  coords,
  selected,
  readOnly,
  onSelect,
  onChangeRect,
  bgUrl,
}: {
  width: number;
  height: number;
  coords: PixelRect[];
  selected: number | null;
  readOnly: boolean;
  onSelect: (index: number | null) => void;
  onChangeRect: (index: number, rect: PixelRect) => void;
  bgUrl?: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragMode | null>(null);

  const toPx = useCallback(
    (e: React.MouseEvent | MouseEvent): [number, number] => {
      const rect = wrapRef.current!.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * width;
      const y = ((e.clientY - rect.top) / rect.height) * height;
      return [Math.max(0, Math.min(width, x)), Math.max(0, Math.min(height, y))];
    },
    [width, height],
  );

  const screenTol = () => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 12;
    return (HANDLE / rect.width) * width;
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (readOnly) return;
    e.preventDefault();
    const [x, y] = toPx(e);
    const tol = screenTol();

    if (selected != null && coords[selected]) {
      const edge = edgeAt(coords[selected], x, y, tol);
      if (edge) {
        setDrag({
          kind: 'resize',
          index: selected,
          edge,
          startX: x,
          startY: y,
          orig: [...coords[selected]] as PixelRect,
        });
        return;
      }
    }

    const hit = hitTest(coords, x, y);
    if (hit != null) {
      onSelect(hit);
      const edge = edgeAt(coords[hit], x, y, tol);
      if (edge) {
        setDrag({
          kind: 'resize',
          index: hit,
          edge,
          startX: x,
          startY: y,
          orig: [...coords[hit]] as PixelRect,
        });
      } else {
        setDrag({
          kind: 'move',
          index: hit,
          startX: x,
          startY: y,
          orig: [...coords[hit]] as PixelRect,
        });
      }
      return;
    }
    onSelect(null);
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag) return;
    const [x, y] = toPx(e);
    if (drag.kind === 'move') {
      const dx = x - drag.startX;
      const dy = y - drag.startY;
      const [ox, oy, ow, oh] = drag.orig;
      const nx = Math.max(0, Math.min(width - ow, ox + dx));
      const ny = Math.max(0, Math.min(height - oh, oy + dy));
      onChangeRect(drag.index, [nx, ny, ow, oh]);
      return;
    }
    onChangeRect(drag.index, applyResize(drag.orig, drag.edge, x, y, width, height));
  };

  const endDrag = () => setDrag(null);

  const cursorFor = (): string => {
    if (readOnly) return 'default';
    if (drag?.kind === 'move') return 'move';
    if (drag?.kind === 'resize') {
      const e = drag.edge;
      if (e === 'n' || e === 's') return 'ns-resize';
      if (e === 'e' || e === 'w') return 'ew-resize';
      if (e === 'ne' || e === 'sw') return 'nesw-resize';
      return 'nwse-resize';
    }
    return 'default';
  };

  return (
    <div
      ref={wrapRef}
      className="source-split-canvas"
      style={{
        aspectRatio: `${Math.max(width, 1)} / ${Math.max(height, 1)}`,
        backgroundImage: bgUrl ? `url(${bgUrl})` : undefined,
        cursor: cursorFor(),
      }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
    >
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="source-split-svg">
        {coords.map((r, i) => {
          const active = selected === i;
          const [rx, ry, rw, rh] = r;
          return (
            <g key={i}>
              <rect
                x={rx}
                y={ry}
                width={rw}
                height={rh}
                className={active ? 'source-split-rect active' : 'source-split-rect'}
              />
              <text x={rx + 8} y={ry + 20} className="source-split-label">
                #{i}
              </text>
              {active && !readOnly
                ? (
                    [
                      [rx, ry],
                      [rx + rw / 2, ry],
                      [rx + rw, ry],
                      [rx, ry + rh / 2],
                      [rx + rw, ry + rh / 2],
                      [rx, ry + rh],
                      [rx + rw / 2, ry + rh],
                      [rx + rw, ry + rh],
                    ] as [number, number][]
                  ).map(([hx, hy], hi) => (
                    <rect
                      key={hi}
                      x={hx - width * 0.006}
                      y={hy - height * 0.006}
                      width={width * 0.012}
                      height={height * 0.012}
                      className="source-split-handle"
                    />
                  ))
                : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
