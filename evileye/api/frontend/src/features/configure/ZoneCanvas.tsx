import { useEffect, useRef, useState } from 'react';
import { editorsApi, type ZoneItem } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function ZoneCanvas({
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
  const [zones, setZones] = useState<ZoneItem[]>([]);
  const [mode, setMode] = useState<'rect' | 'polygon'>('rect');
  const [draft, setDraft] = useState<[number, number][]>([]);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void editorsApi
      .getZones(configName, sourceId)
      .then((r) => setZones(r.zones ?? []))
      .catch((e) => showError(e.message));
  }, [configName, sourceId, showError]);

  const toNorm = (e: React.MouseEvent): [number, number] => {
    const rect = wrapRef.current!.getBoundingClientRect();
    return [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height];
  };

  return (
    <div>
      <div className="toolbar">
        <label>
          source_id{' '}
          <input type="number" min={0} value={sourceId} onChange={(e) => onSourceIdChange(Number(e.target.value))} />
        </label>
        <Button size="sm" variant={mode === 'rect' ? 'primary' : 'outline'} onClick={() => setMode('rect')}>
          Rect
        </Button>
        <Button size="sm" variant={mode === 'polygon' ? 'primary' : 'outline'} onClick={() => setMode('polygon')}>
          Polygon
        </Button>
        {!readOnly ? (
          <Button
            variant="primary"
            onClick={() =>
              void editorsApi
                .putZones(configName, sourceId, zones)
                .then((r) => showSuccess(r.restart_required ? 'Сохранено (нужен restart)' : 'Сохранено'))
                .catch((e) => showError(e.message))
            }
          >
            Сохранить zones
          </Button>
        ) : null}
      </div>
      <div
        ref={wrapRef}
        style={{ position: 'relative', width: '100%', maxWidth: 640, aspectRatio: '16/9', background: '#111', border: '1px solid var(--border)' }}
        onClick={(e) => {
          if (readOnly) return;
          const p = toNorm(e);
          if (mode === 'polygon') {
            setDraft((d) => [...d, p]);
            return;
          }
          if (draft.length === 0) setDraft([p]);
          else {
            const a = draft[0];
            setZones((z) => [
              ...z,
              {
                type: 'rect',
                name: `zone_${z.length + 1}`,
                points: [a, [p[0], a[1]], p, [a[0], p[1]]],
              },
            ]);
            setDraft([]);
          }
        }}
        onDoubleClick={() => {
          if (mode === 'polygon' && draft.length >= 3) {
            setZones((z) => [...z, { type: 'polygon', name: `zone_${z.length + 1}`, points: draft }]);
            setDraft([]);
          }
        }}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          {zones.map((z, i) => (
            <polygon
              key={i}
              points={z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
              fill="rgba(59,130,246,0.15)"
              stroke="#3b82f6"
              strokeWidth="2"
            />
          ))}
          {draft.length ? (
            <polyline
              points={draft.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2"
            />
          ) : null}
        </svg>
      </div>
      <p className="hint">Rect: два клика. Polygon: клики + double-click для замыкания.</p>
    </div>
  );
}
