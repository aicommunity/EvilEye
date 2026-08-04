import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { FormActions, FormField, FormGrid } from '../formLayout';

type FieldDef =
  | { key: string; label: string; kind: 'bool' }
  | { key: string; label: string; kind: 'number' }
  | { key: string; label: string; kind: 'text' }
  | { key: string; label: string; kind: 'json' };

function asObj(data: unknown): Record<string, unknown> {
  return data && typeof data === 'object' && !Array.isArray(data) ? { ...(data as Record<string, unknown>) } : {};
}

/** Object form: known fields + merge unknown keys on save. Supports onChange for dirty tracking. */
export function ObjectSectionForm({
  title,
  fields,
  data,
  readOnly,
  onSave,
  onChange,
}: {
  title: string;
  fields: FieldDef[];
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const { t } = useI18n();
  const [obj, setObj] = useState(() => asObj(data));
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState('{}');

  useEffect(() => {
    const next = asObj(data);
    setObj(next);
    setJsonText(JSON.stringify(data ?? {}, null, 2));
  }, [data]);

  const update = (next: Record<string, unknown>) => {
    setObj(next);
    onChange?.(next);
  };

  if (jsonMode) {
    return (
      <div className="config-studio-json">
        <p className="hint">{title} — {t('common.json')}</p>
        <textarea
          value={jsonText}
          readOnly={readOnly}
          onChange={(e) => {
            setJsonText(e.target.value);
            try {
              onChange?.(JSON.parse(e.target.value || '{}'));
            } catch {
              /* ignore while typing */
            }
          }}
        />
        <FormActions>
          <Button size="sm" variant="outline" onClick={() => setJsonMode(false)}>
            {t('configure.forms.fields')}
          </Button>
          {!readOnly ? (
            <Button variant="primary" onClick={() => void onSave(JSON.parse(jsonText || '{}'))}>
              {t('configure.forms.save')}
            </Button>
          ) : null}
        </FormActions>
      </div>
    );
  }

  return (
    <div>
      <p className="hint">{title}</p>
      <FormGrid>
        {fields.map((f) => {
          const value = obj[f.key];
          if (f.kind === 'bool') {
            return (
              <FormField key={f.key} label={f.label}>
                <input
                  type="checkbox"
                  disabled={readOnly}
                  checked={Boolean(value)}
                  onChange={(e) => update({ ...obj, [f.key]: e.target.checked })}
                />
              </FormField>
            );
          }
          if (f.kind === 'json') {
            const text = typeof value === 'string' ? value : JSON.stringify(value ?? '', null, 0);
            return (
              <FormField key={f.key} label={f.label} fullWidth>
                <input
                  disabled={readOnly}
                  value={text === '""' || text === 'null' ? '' : String(text).replace(/^"|"$/g, '')}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    if (!raw) {
                      update({ ...obj, [f.key]: undefined });
                      return;
                    }
                    try {
                      update({ ...obj, [f.key]: JSON.parse(raw) });
                    } catch {
                      update({ ...obj, [f.key]: raw });
                    }
                  }}
                />
              </FormField>
            );
          }
          return (
            <FormField key={f.key} label={f.label}>
              <input
                disabled={readOnly}
                type={f.kind === 'number' ? 'number' : 'text'}
                value={value == null ? '' : String(value)}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (f.kind === 'number') {
                    update({ ...obj, [f.key]: raw === '' ? undefined : Number(raw) });
                  } else {
                    update({ ...obj, [f.key]: raw });
                  }
                }}
              />
            </FormField>
          );
        })}
      </FormGrid>
      <FormActions>
        <Button size="sm" variant="outline" onClick={() => setJsonMode(true)}>
          JSON
        </Button>
        {!readOnly ? (
          <Button variant="primary" onClick={() => void onSave(obj)}>
            {t('configure.forms.save')}
          </Button>
        ) : null}
      </FormActions>
    </div>
  );
}
