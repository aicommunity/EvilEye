import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';

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
  onChange,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<TrackerRow[]>(() => asRows(data));
  useEffect(() => setRows(asRows(data)), [data]);
  const updateRows = (next: TrackerRow[]) => {
    setRows(next);
    onChange?.(next);
  };

  return (
    <div>
      <p className="hint">{t('configure.forms.hintTrackers')}</p>
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
            max_age{' '}
            <input
              type="number"
              disabled={readOnly}
              value={row.max_age ?? ''}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, max_age: e.target.value === '' ? undefined : Number(e.target.value) };
                updateRows(next);
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
                updateRows(next);
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
                updateRows(next);
              }}
              style={{ width: 80 }}
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
            <Button size="sm" variant="outline" onClick={() => updateRows([...rows, { name: 'tracker', max_age: 30 }])}>
              {t('configure.forms.addTracker')}
            </Button>
            <Button variant="primary" onClick={() => void onSave(Array.isArray(data) ? rows : rows[0] ?? {})}>
              {t('configure.forms.saveSection', { section: 'trackers' })}
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
