import { useEffect, useRef, useState } from 'react';
import { editorsApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function RoiCanvas({
  configName,
  sourceId,
  onSourceIdChange,
  readOnly,
}: {
  configName: string;
  sourceId: number;
  onSourceIdChange: (id: number) => void;
  readOnly: boolean;
}) {
  const { showError, showSuccess } = useToast();
  const [rois, setRois] = useState<number[][]>([]);
  const [drawing, setDrawing] = useState<number[] | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void editorsApi
      .getRoi(configName, sourceId)
      .then((r) => setRois(r.rois ?? []))
      .catch((e) => showError(e.message));
  }, [configName, sourceId, showError]);

  const toNorm = (e: React.MouseEvent) => {
    const rect = wrapRef.current!.getBoundingClientRect();
    return [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height] as [number, number];
  };

  return (
    <div>
      <div className="toolbar">
        <label>
          source_id{' '}
          <input type="number" min={0} value={sourceId} onChange={(e) => onSourceIdChange(Number(e.target.value))} />
        </label>
        {!readOnly ? (
          <Button
            variant="primary"
            onClick={() =>
              void editorsApi
                .putRoi(configName, sourceId, rois)
                .then((r) => showSuccess(r.restart_required ? 'Сохранено (нужен restart)' : 'Сохранено'))
                .catch((e) => showError(e.message))
            }
          >
            Сохранить ROI
          </Button>
        ) : null}
      </div>
      <div
        ref={wrapRef}
        style={{ position: 'relative', width: '100%', maxWidth: 640, aspectRatio: '16/9', background: '#111', border: '1px solid var(--border)' }}
        onMouseDown={(e) => {
          if (readOnly) return;
          const [x, y] = toNorm(e);
          setDrawing([x, y, x, y]);
        }}
        onMouseMove={(e) => {
          if (!drawing) return;
          const [x, y] = toNorm(e);
          setDrawing([drawing[0], drawing[1], x, y]);
        }}
        onMouseUp={() => {
          if (!drawing) return;
          setRois((prev) => [...prev, drawing]);
          setDrawing(null);
        }}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          {[...rois, ...(drawing ? [drawing] : [])].map((r, i) => {
            const [x1, y1, x2, y2] = r;
            return (
              <rect
                key={i}
                x={Math.min(x1, x2) * 100}
                y={Math.min(y1, y2) * 100}
                width={Math.abs(x2 - x1) * 100}
                height={Math.abs(y2 - y1) * 100}
                fill="rgba(34,197,94,0.15)"
                stroke="#22c55e"
                strokeWidth="2"
              />
            );
          })}
        </svg>
      </div>
      <Button size="sm" variant="outline" disabled={readOnly} onClick={() => setRois([])}>
        Очистить
      </Button>
    </div>
  );
}
