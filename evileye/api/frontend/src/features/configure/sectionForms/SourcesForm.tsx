import { useEffect, useMemo, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { FormActions, FormField, FormGrid } from '../formLayout';
import { SourceAdvancedEditor } from '../SourceAdvancedEditor';
import {
  applyRegionsToRow,
  cloneSourceRow,
  collectOccupiedSourceIds,
  padRegions,
  parseSourceRegions,
} from '../sourceRowUtils';
import { formatInt, INT_STEP, parseIntInput } from '../numberFormat';

type SourceRow = {
  source?: string;
  type?: string;
  camera?: string;
  source_ids?: unknown;
  source_names?: unknown;
  split?: boolean;
  num_split?: number;
  src_coords?: unknown;
  execution_mode?: string;
  loop_play?: boolean;
  desired_fps?: number;
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
  onChange,
  configName,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
  configName: string;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<SourceRow[]>(() => asRows(data));
  const [advanced, setAdvanced] = useState(false);
  const [jsonText, setJsonText] = useState('[]');
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editSnapshot, setEditSnapshot] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const next = asRows(data);
    setRows(next);
    setJsonText(JSON.stringify(Array.isArray(data) ? data : next, null, 2));
  }, [data]);

  const updateRows = (next: SourceRow[]) => {
    setRows(next);
    onChange?.(next);
  };

  const openAdvanced = (i: number) => {
    setEditSnapshot(cloneSourceRow(rows[i] as Record<string, unknown>));
    setEditIndex(i);
  };

  const occupiedForEdit = useMemo(() => {
    if (editIndex == null) return [] as number[];
    return [...collectOccupiedSourceIds(rows as Record<string, unknown>[], editIndex)];
  }, [editIndex, rows]);

  if (advanced) {
    return (
      <div className="config-studio-json">
        <p className="hint">{t('configure.forms.hintSourcesJson')}</p>
        <textarea
          value={jsonText}
          readOnly={readOnly}
          onChange={(e) => {
            setJsonText(e.target.value);
            try {
              onChange?.(JSON.parse(e.target.value || '[]'));
            } catch {
              /* ignore */
            }
          }}
        />
        <FormActions>
          <Button size="sm" variant="outline" onClick={() => setAdvanced(false)}>
            {t('configure.forms.fields')}
          </Button>
          {!readOnly ? (
            <Button variant="primary" onClick={() => void onSave(JSON.parse(jsonText || '[]'))}>
              {t('configure.forms.save')}
            </Button>
          ) : null}
        </FormActions>
      </div>
    );
  }

  return (
    <div>
      <p className="hint">{t('configure.forms.hintSources')}</p>
      {rows.map((row, i) => (
        <div key={i} className="config-source-block">
          <FormGrid>
            <FormField label="source / uri">
              <input
                disabled={readOnly}
                value={String(row.source ?? row.uri ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, source: e.target.value, uri: e.target.value };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="type">
              <input
                disabled={readOnly}
                value={String(row.type ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, type: e.target.value };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="camera">
              <input
                disabled={readOnly}
                value={String(row.camera ?? row.source_name ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, camera: e.target.value, source_name: e.target.value };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="desired_fps / fps">
              <input
                type="number"
                step={INT_STEP}
                disabled={readOnly}
                value={
                  row.desired_fps != null || row.fps != null
                    ? formatInt(Number(row.desired_fps ?? row.fps))
                    : ''
                }
                onChange={(e) => {
                  const next = [...rows];
                  const n = parseIntInput(e.target.value);
                  next[i] = { ...row, desired_fps: n, fps: n };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="execution_mode">
              <input
                disabled={readOnly}
                value={String(row.execution_mode ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, execution_mode: e.target.value };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="loop_play">
              <input
                type="checkbox"
                disabled={readOnly}
                checked={Boolean(row.loop_play)}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, loop_play: e.target.checked };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="split">
              <input
                type="checkbox"
                disabled={readOnly}
                checked={Boolean(row.split)}
                onChange={(e) => {
                  const next = [...rows];
                  const asRec = row as Record<string, unknown>;
                  const parsed = parseSourceRegions(asRec);
                  const occupied = collectOccupiedSourceIds(rows as Record<string, unknown>[], i);
                  if (e.target.checked) {
                    const padded = padRegions(2, parsed.ids, parsed.names, parsed.coords, 1920, 1080, occupied);
                    next[i] = applyRegionsToRow(asRec, { split: true, ...padded }) as SourceRow;
                  } else {
                    next[i] = applyRegionsToRow(asRec, {
                      split: false,
                      ids: [parsed.ids[0] ?? 0],
                      names: [parsed.names[0] ?? `Cam${(parsed.ids[0] ?? 0) + 1}`],
                      coords: [],
                    }) as SourceRow;
                  }
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="num_split">
              <input
                type="number"
                step={INT_STEP}
                disabled={readOnly}
                value={row.num_split != null ? formatInt(Number(row.num_split)) : ''}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = { ...row, num_split: parseIntInput(e.target.value) };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="source_ids (CSV)">
              <input
                disabled={readOnly}
                value={Array.isArray(row.source_ids) ? row.source_ids.join(',') : String(row.source_ids ?? row.source_id ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  const ids = e.target.value
                    .split(',')
                    .map((x) => x.trim())
                    .filter(Boolean)
                    .map(Number)
                    .filter((n) => !Number.isNaN(n));
                  next[i] = { ...row, source_ids: ids };
                  updateRows(next);
                }}
              />
            </FormField>
            <FormField label="source_names (CSV)">
              <input
                disabled={readOnly}
                value={Array.isArray(row.source_names) ? row.source_names.join(',') : String(row.source_names ?? '')}
                onChange={(e) => {
                  const next = [...rows];
                  next[i] = {
                    ...row,
                    source_names: e.target.value
                      .split(',')
                      .map((x) => x.trim())
                      .filter(Boolean),
                  };
                  updateRows(next);
                }}
              />
            </FormField>
          </FormGrid>
          <div className="config-source-block__actions">
            <Button size="sm" variant="outline" onClick={() => openAdvanced(i)}>
              {t('setup.sourceAdvanced')}
            </Button>
            {!readOnly ? (
              <Button size="sm" variant="outline" onClick={() => updateRows(rows.filter((_, j) => j !== i))}>
                {t('configure.forms.removeSource')}
              </Button>
            ) : null}
          </div>
        </div>
      ))}
      <FormActions>
        {!readOnly ? (
          <>
            <Button size="sm" variant="outline" onClick={() => updateRows([...rows, { source: '', type: 'video_file' }])}>
              {t('configure.forms.addSource')}
            </Button>
            <Button variant="primary" onClick={() => void onSave(rows)}>
              {t('configure.forms.saveSection', { section: 'sources' })}
            </Button>
          </>
        ) : null}
        <Button size="sm" variant="outline" onClick={() => setAdvanced(true)}>
          JSON
        </Button>
      </FormActions>

      <SourceAdvancedEditor
        open={editIndex != null}
        configName={configName}
        sourceIndex={editIndex ?? 0}
        initialRow={editSnapshot ?? {}}
        occupiedIds={occupiedForEdit}
        readOnly={readOnly}
        onClose={() => {
          setEditIndex(null);
          setEditSnapshot(null);
        }}
        onApplied={async (row) => {
          if (editIndex == null) return;
          const next = [...rows];
          next[editIndex] = row as SourceRow;
          updateRows(next);
          await onSave(next);
          setEditIndex(null);
          setEditSnapshot(null);
        }}
      />
    </div>
  );
}
