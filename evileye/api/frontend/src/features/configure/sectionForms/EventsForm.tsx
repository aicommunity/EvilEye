import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

type EventRow = {
  name?: string;
  type?: string;
  source_ids?: number[];
  classes?: unknown;
  [key: string]: unknown;
};

function asRows(data: unknown): EventRow[] {
  return Array.isArray(data) ? (data as EventRow[]) : data && typeof data === 'object' ? [data as EventRow] : [];
}

export function EventsForm({
  data,
  readOnly,
  onSave,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const [rows, setRows] = useState<EventRow[]>(() => asRows(data));
  useEffect(() => setRows(asRows(data)), [data]);

  return (
    <div>
      <p className="hint">Детекторы событий. Зоны рисуйте на вкладке Zones.</p>
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
            type{' '}
            <input
              disabled={readOnly}
              value={String(row.type ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, type: e.target.value };
                setRows(next);
              }}
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
                setRows(next);
              }}
              style={{ width: 100 }}
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
            <Button size="sm" variant="outline" onClick={() => setRows([...rows, { name: 'event', type: 'zone' }])}>
              + event
            </Button>
            <Button variant="primary" onClick={() => void onSave(Array.isArray(data) || !data ? rows : rows[0] ?? {})}>
              Сохранить events
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
