import { useEffect, useRef, useState } from 'react';
import type { StateCamera } from '../../api';
import { useI18n } from '../../i18n';
import { CameraTile } from './CameraTile';

export function CameraGrid({
  cameras,
  cols,
  onOpenStream,
  onReorder,
  onExpand,
  getPreviewBlob,
  previewWsActive = false,
}: {
  cameras: StateCamera[];
  cols: number;
  onOpenStream: (rid: number, sid: number | null) => void;
  onReorder: (keys: string[]) => void;
  onExpand?: (key: string) => void;
  getPreviewBlob?: (sourceId: number | null) => string | null | undefined;
  previewWsActive?: boolean;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<string>>(new Set());
  const dragKey = useRef<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const elByKey = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      (entries) => {
        setVisible((prev) => {
          const next = new Set(prev);
          for (const entry of entries) {
            const key = (entry.target as HTMLElement).dataset.camKey;
            if (!key) continue;
            if (entry.isIntersecting) next.add(key);
            else next.delete(key);
          }
          return next;
        });
      },
      { threshold: 0.25, rootMargin: '40px' },
    );
    elByKey.current.forEach((el) => observerRef.current?.observe(el));
    return () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    };
  }, []);

  if (!cameras.length) {
    return <p className="empty">{t('live.camera.unavailable')}</p>;
  }

  const keyOf = (c: StateCamera) => `${c.run_id}:${c.source_id}`;

  return (
    <div className="camera-group-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {cameras.map((camera) => {
        const key = keyOf(camera);
        const isSelected = selected === key;
        const isVisible = visible.has(key) || isSelected;
        return (
          <div
            key={key}
            data-cam-key={key}
            ref={(el) => {
              const obs = observerRef.current;
              const prev = elByKey.current.get(key);
              if (prev && obs) obs.unobserve(prev);
              if (el) {
                el.dataset.camKey = key;
                elByKey.current.set(key, el);
                obs?.observe(el);
              } else {
                elByKey.current.delete(key);
              }
            }}
            onClick={() => setSelected(key)}
            style={{ outline: isSelected ? '2px solid var(--accent)' : undefined, borderRadius: 8 }}
          >
            <CameraTile
              camera={camera}
              useMjpeg={false}
              gridMode
              active={isVisible}
              previewBlobUrl={getPreviewBlob?.(camera.source_id) ?? null}
              previewWsActive={previewWsActive}
              onOpen={() => onOpenStream(camera.run_id, camera.source_id)}
              onExpand={onExpand ? () => onExpand(key) : undefined}
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
