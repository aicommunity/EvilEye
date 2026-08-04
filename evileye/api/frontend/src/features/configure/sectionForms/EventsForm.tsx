import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';

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
  onChange,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<EventRow[]>(() => asRows(data));
  useEffect(() => setRows(asRows(data)), [data]);
  const updateRows = (next: EventRow[]) => {
    setRows(next);
    onChange?.(next);
  };

  return (
    <div>
      <p className="hint">{t('configure.forms.hintEvents')}</p>
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
                updateRows(next);
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
                updateRows(next);
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
                updateRows(next);
              }}
              style={{ width: 100 }}
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
            <Button size="sm" variant="outline" onClick={() => updateRows([...rows, { name: 'event', type: 'zone' }])}>
              {t('configure.forms.addEvent')}
            </Button>
            <Button variant="primary" onClick={() => void onSave(Array.isArray(data) || !data ? rows : rows[0] ?? {})}>
              {t('configure.forms.saveSection', { section: 'events' })}
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
