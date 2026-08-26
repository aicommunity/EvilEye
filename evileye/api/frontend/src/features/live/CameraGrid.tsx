import { useEffect, useRef, useState } from 'react';
import type { StateCamera } from '../../api';
import { useI18n } from '../../i18n';
import { CameraTile } from './CameraTile';
import { cameraTileActive } from './livePreviewPrefer';

export function CameraGrid({
  cameras,
  cols,
  mode = 'fixed',
  onOpenStream,
  onReorder,
  onExpand,
  getPreviewBlob,
  getPreviewFrameAgeSec,
  previewWsActive = false,
  loading = false,
  camerasPolledAtMs,
  healthTick = 0,
  onActiveSourcesChange,
}: {
  cameras: StateCamera[];
  cols: number;
  mode?: 'fit' | 'fixed';
  onOpenStream: (rid: number, sid: number | null) => void;
  onReorder: (keys: string[]) => void;
  onExpand?: (key: string) => void;
  getPreviewBlob?: (sourceId: number | null) => string | null | undefined;
  getPreviewFrameAgeSec?: (sourceId: number | null) => number | null | undefined;
  previewWsActive?: boolean;
  loading?: boolean;
  camerasPolledAtMs?: number;
  healthTick?: number;
  /** C3: report currently active (visible) sources for per-source demand. */
  onActiveSourcesChange?: (active: Array<{ runId: number; sourceId: number | null }>) => void;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<string>>(new Set());
  /** Until the first IntersectionObserver callback, treat all tiles as active (fixed cold start). */
  const [ioReady, setIoReady] = useState(false);
  const dragKey = useRef<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const elByKey = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    setIoReady(false);
    observerRef.current = new IntersectionObserver(
      (entries) => {
        setIoReady(true);
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

  const keyOf = (c: StateCamera) => `${c.run_id}:${c.source_id}`;

  useEffect(() => {
    if (!onActiveSourcesChange) return;
    const activeCams = cameras.filter((camera) => {
      const key = keyOf(camera);
      return cameraTileActive({
        mode,
        ioReady,
        visible: visible.has(key),
        selected: selected === key,
      });
    });
    onActiveSourcesChange(
      activeCams.map((c) => ({ runId: c.run_id, sourceId: c.source_id ?? null })),
    );
  }, [cameras, mode, ioReady, visible, selected, onActiveSourcesChange]);

  if (!cameras.length) {
    return (
      <p className="empty">{loading ? t('common.searching') : t('live.camera.unavailable')}</p>
    );
  }

  return (
    <div
      className={`camera-group-grid${mode === 'fit' ? ' camera-group-grid--fit' : ''}`}
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {cameras.map((camera) => {
        const key = keyOf(camera);
        const isSelected = selected === key;
        const isVisible = cameraTileActive({
          mode,
          ioReady,
          visible: visible.has(key),
          selected: isSelected,
        });
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
              previewFrameAgeSec={getPreviewFrameAgeSec?.(camera.source_id) ?? null}
              camerasPolledAtMs={camerasPolledAtMs}
              healthTick={healthTick}
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
