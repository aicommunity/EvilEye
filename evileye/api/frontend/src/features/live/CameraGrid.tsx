import { useRef, useState } from 'react';
import type { StateCamera } from '../../api';
import { CameraTile } from './CameraTile';

export function CameraGrid({
  cameras,
  cols,
  onOpenStream,
  onReorder,
}: {
  cameras: StateCamera[];
  cols: number;
  onOpenStream: (rid: number, sid: number | null) => void;
  onReorder: (keys: string[]) => void;
}) {
  const [focused, setFocused] = useState<string | null>(null);
  const dragKey = useRef<string | null>(null);

  if (!cameras.length) {
    return <p className="empty">Камеры текущего запуска недоступны.</p>;
  }

  const keyOf = (c: StateCamera) => `${c.run_id}:${c.source_id}`;

  return (
    <div className="camera-group-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {cameras.map((camera) => {
        const key = keyOf(camera);
        const useMjpeg = focused === key;
        return (
          <div
            key={key}
            onClick={() => setFocused(key)}
            style={{ outline: focused === key ? '2px solid var(--accent)' : undefined, borderRadius: 8 }}
          >
            <CameraTile
              camera={camera}
              useMjpeg={useMjpeg}
              onOpen={() => onOpenStream(camera.run_id, camera.source_id)}
              draggable
              onDragStart={() => {
                dragKey.current = key;
              }}
              onDrop={() => {
                const from = dragKey.current;
                if (!from || from === key) return;
                const keys = cameras.map(keyOf);
                const fi = keys.indexOf(from);
                const ti = keys.indexOf(key);
                if (fi < 0 || ti < 0) return;
                const next = [...keys];
                next.splice(fi, 1);
                next.splice(ti, 0, from);
                onReorder(next);
                dragKey.current = null;
              }}
            />
          </div>
        );
      })}
    </div>
  );
}
