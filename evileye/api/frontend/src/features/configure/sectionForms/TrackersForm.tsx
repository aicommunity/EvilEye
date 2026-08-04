import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

type TrackerRow = {
  name?: string;
  max_age?: number;
  min_hits?: number;
  iou_threshold?: number;
  source_ids?: number[];
  [key: string]: unknown;
};

function asRows(data: unknown): TrackerRow[] {
  return Array.isArray(data) ? (data as TrackerRow[]) : data && typeof data === 'object' ? [data as TrackerRow] : [];
}

export function TrackersForm({
  data,
  readOnly,
  onSave,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const [rows, setRows] = useState<TrackerRow[]>(() => asRows(data));
  useEffect(() => setRows(asRows(data)), [data]);

  return (
    <div>
      <p className="hint">Трекеры: max_age, min_hits, iou_threshold, source_ids.</p>
      {rows.map((row, i) => (
        <div key={i} className="toolbar" style={{ flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          <label>
            name{' '}
            <input
              disabled={readOnly}
              value={String(row.name ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, name: e.target.value };
                setRows(next);
              }}
            />
          </label>
          <label>
            max_age{' '}
            <input
              type="number"
              disabled={readOnly}
              value={row.max_age ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, max_age: e.target.value === '' ? undefined : Number(e.target.value) };
                setRows(next);
              }}
              style={{ width: 80 }}
            />
          </label>
          <label>
            min_hits{' '}
            <input
              type="number"
              disabled={readOnly}
              value={row.min_hits ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, min_hits: e.target.value === '' ? undefined : Number(e.target.value) };
                setRows(next);
              }}
              style={{ width: 80 }}
            />
          </label>
          <label>
            iou{' '}
            <input
              type="number"
              step="0.01"
              disabled={readOnly}
              value={row.iou_threshold ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, iou_threshold: e.target.value === '' ? undefined : Number(e.target.value) };
                setRows(next);
              }}
              style={{ width: 80 }}
            />
          </label>
          {!readOnly ? (
            <Button size="sm" variant="outline" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              −
            </Button>
          ) : null}
        </div>
      ))}
      <div className="toolbar">
        {!readOnly ? (
          <>
            <Button size="sm" variant="outline" onClick={() => setRows([...rows, { name: 'tracker', max_age: 30 }])}>
              + tracker
            </Button>
            <Button variant="primary" onClick={() => void onSave(Array.isArray(data) ? rows : rows[0] ?? {})}>
              Сохранить trackers
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
