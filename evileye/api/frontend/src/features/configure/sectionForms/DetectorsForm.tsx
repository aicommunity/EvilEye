import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

type DetectorRow = {
  model?: string;
  conf?: number;
  classes?: unknown;
  source_ids?: number[];
  [key: string]: unknown;
};

function asRows(data: unknown): DetectorRow[] {
  return Array.isArray(data) ? (data as DetectorRow[]) : [];
}

export function DetectorsForm({
  data,
  readOnly,
  onSave,
  onChange,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const [rows, setRows] = useState<DetectorRow[]>(() => asRows(data));

  useEffect(() => setRows(asRows(data)), [data]);
  const updateRows = (next: DetectorRow[]) => {
    setRows(next);
    onChange?.(next);
  };

  return (
    <div>
      <p className="hint">Детекторы: model, classes, source_ids, conf. ROI — вкладка ROI.</p>
      {rows.map((row, i) => (
        <div key={i} className="toolbar" style={{ flexWrap: 'wrap', marginBottom: 8, gap: 8 }}>
          <label>
            model{' '}
            <input
              disabled={readOnly}
              value={String(row.model ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, model: e.target.value };
                updateRows(next);
              }}
              style={{ minWidth: 180 }}
            />
          </label>
          <label>
            conf{' '}
            <input
              type="number"
              step="0.01"
              min={0}
              max={1}
              disabled={readOnly}
              value={row.conf ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, conf: e.target.value === '' ? undefined : Number(e.target.value) };
                updateRows(next);
              }}
              style={{ width: 80 }}
            />
          </label>
          <label>
            source_ids{' '}
            <input
              disabled={readOnly}
              value={(row.source_ids ?? []).join(',')}
              onChange={(e) => {
                const ids = e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean)
                  .map(Number)
                  .filter((n) => !Number.isNaN(n));
                const next = [...rows];
                next[i] = { ...row, source_ids: ids };
                updateRows(next);
              }}
              placeholder="0,1"
              style={{ width: 100 }}
            />
          </label>
          <label>
            classes{' '}
            <input
              disabled={readOnly}
              value={Array.isArray(row.classes) ? row.classes.join(',') : String(row.classes ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = {
                  ...row,
                  classes: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                    .map((v) => (/^\d+$/.test(v) ? Number(v) : v)),
                };
                updateRows(next);
              }}
              style={{ minWidth: 120 }}
            />
          </label>
          {!readOnly ? (
            <Button size="sm" variant="outline" onClick={() => updateRows(rows.filter((_, j) => j !== i))}>
              −
            </Button>
          ) : null}
        </div>
      ))}
      <div className="toolbar">
        {!readOnly ? (
          <>
            <Button size="sm" variant="outline" onClick={() => updateRows([...rows, { model: '', conf: 0.25, source_ids: [] }])}>
              + детектор
            </Button>
            <Button variant="primary" onClick={() => void onSave(rows)}>
              Сохранить detectors
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
