import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { FormActions, FormField, FormGrid } from '../formLayout';

function asObj(data: unknown): Record<string, unknown> {
  return data && typeof data === 'object' && !Array.isArray(data) ? { ...(data as Record<string, unknown>) } : {};
}

/** Toggle enable flags for nested adapter objects; JSON for complex values. */
export function DatabaseAdaptersForm({
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
  const [obj, setObj] = useState(() => asObj(data));
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState('{}');

  useEffect(() => {
    setObj(asObj(data));
    setJsonText(JSON.stringify(data ?? {}, null, 2));
  }, [data]);

  const update = (next: Record<string, unknown>) => {
    setObj(next);
    onChange?.(next);
  };

  if (jsonMode) {
    return (
      <div className="config-studio-json">
        <textarea
          value={jsonText}
          readOnly={readOnly}
          onChange={(e) => {
            setJsonText(e.target.value);
            try {
              onChange?.(JSON.parse(e.target.value || '{}'));
            } catch {
              /* ignore */
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

  const entries = Object.entries(obj);

  return (
    <div>
      <p className="hint">{t('configure.forms.hintAdapters')}</p>
      <FormGrid>
        {entries.map(([key, value]) => {
          const enabled =
            value && typeof value === 'object' && !Array.isArray(value)
              ? Boolean((value as { enabled?: boolean }).enabled)
              : Boolean(value);
          return (
            <FormField key={key} label={key}>
              <input
                type="checkbox"
                disabled={readOnly}
                checked={enabled}
                onChange={(e) => {
                  if (value && typeof value === 'object' && !Array.isArray(value)) {
                    update({ ...obj, [key]: { ...(value as object), enabled: e.target.checked } });
                  } else {
                    update({ ...obj, [key]: e.target.checked });
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
