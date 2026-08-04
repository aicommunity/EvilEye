import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

type SourceRow = {
  source_id?: number;
  source_name?: string;
  uri?: string;
  fps?: number;
  [key: string]: unknown;
};

function asRows(data: unknown): SourceRow[] {
  if (Array.isArray(data)) return data as SourceRow[];
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: SourceRow[] }).items;
  }
  return [];
}

export function SourcesForm({
  data,
  readOnly,
  onSave,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const [rows, setRows] = useState<SourceRow[]>(() => asRows(data));
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => setRows(asRows(data)), [data]);

  if (advanced) {
    const text = JSON.stringify(Array.isArray(data) ? rows : data ?? rows, null, 2);
    return (
      <div>
        <p className="hint">Advanced JSON для sources.</p>
        <textarea rows={16} defaultValue={text} key={text} readOnly={readOnly} id="sources-form-json" />
        <div className="toolbar">
          <Button size="sm" variant="outline" onClick={() => setAdvanced(false)}>
            Поля
          </Button>
          {!readOnly ? (
            <Button
              variant="primary"
              onClick={() => {
                const el = document.getElementById('sources-form-json') as HTMLTextAreaElement;
                void onSave(JSON.parse(el.value || '[]'));
              }}
            >
              Сохранить
            </Button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      <p className="hint">Источники: id, имя, URI, fps.</p>
      {rows.map((row, i) => (
        <div key={i} className="toolbar" style={{ flexWrap: 'wrap', marginBottom: 8, gap: 8 }}>
          <label>
            id{' '}
            <input
              type="number"
              disabled={readOnly}
              value={row.source_id ?? i}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, source_id: Number(e.target.value) };
                setRows(next);
              }}
              style={{ width: 64 }}
            />
          </label>
          <label>
            name{' '}
            <input
              disabled={readOnly}
              value={String(row.source_name ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, source_name: e.target.value };
                setRows(next);
              }}
            />
          </label>
          <label>
            uri{' '}
            <input
              disabled={readOnly}
              value={String(row.uri ?? '')}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, uri: e.target.value };
                setRows(next);
              }}
              style={{ minWidth: 220 }}
            />
          </label>
          <label>
            fps{' '}
            <input
              type="number"
              disabled={readOnly}
              value={row.fps ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, fps: e.target.value === '' ? undefined : Number(e.target.value) };
                setRows(next);
              }}
              style={{ width: 72 }}
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
            <Button size="sm" variant="outline" onClick={() => setRows([...rows, { source_id: rows.length, source_name: '', uri: '' }])}>
              + источник
            </Button>
            <Button variant="primary" onClick={() => void onSave(rows)}>
              Сохранить sources
            </Button>
          </>
        ) : null}
        <Button size="sm" variant="outline" onClick={() => setAdvanced(true)}>
          JSON
        </Button>
      </div>
    </div>
  );
}
