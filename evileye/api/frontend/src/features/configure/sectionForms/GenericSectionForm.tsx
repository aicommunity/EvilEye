import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';

/** Field editor for dict/list sections with common scalar keys. */
export function GenericSectionForm({
  section,
  data,
  readOnly,
  onSave,
  onChange,
}: {
  section: string;
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const { t } = useI18n();
  const [mode, setMode] = useState<'fields' | 'json'>('fields');
  const [obj, setObj] = useState<Record<string, unknown>>({});
  const [jsonText, setJsonText] = useState('{}');

  useEffect(() => {
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      setObj(data as Record<string, unknown>);
      setJsonText(JSON.stringify(data, null, 2));
      setMode('fields');
    } else {
      setJsonText(JSON.stringify(data ?? {}, null, 2));
      setMode('json');
    }
  }, [data]);

  const scalarEntries = Object.entries(obj).filter(
    ([, v]) => v == null || ['string', 'number', 'boolean'].includes(typeof v),
  );

  if (mode === 'json' || !scalarEntries.length) {
    return (
      <div>
        <p className="hint">{t('configure.forms.hintGenericJson', { section })}</p>
        <textarea
          rows={16}
          value={jsonText}
          onChange={(e) => {
            setJsonText(e.target.value);
            try { onChange?.(JSON.parse(e.target.value || '{}')); } catch { /* ignore */ }
          }}
          readOnly={readOnly}
        />
        <div className="toolbar">
          {scalarEntries.length ? (
            <Button size="sm" variant="outline" onClick={() => setMode('fields')}>
            {t('configure.forms.fields')}
            </Button>
          ) : null}
          {!readOnly ? (
            <Button variant="primary" onClick={() => void onSave(JSON.parse(jsonText || '{}'))}>
              {t('configure.forms.saveSection', { section })}
            </Button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      <p className="hint">{t('configure.forms.hintGenericFields', { section })}</p>
      {scalarEntries.map(([key, value]) => (
        <div key={key} className="toolbar" style={{ marginBottom: 6 }}>
          <label style={{ minWidth: 140 }}>{key}</label>
          {typeof value === 'boolean' ? (
            <input
              type="checkbox"
              disabled={readOnly}
              checked={Boolean(value)}
              onChange={(e) => { const next = { ...obj, [key]: e.target.checked }; setObj(next); onChange?.(next); }}
            />
          ) : (
            <input
              disabled={readOnly}
              type={typeof value === 'number' ? 'number' : 'text'}
              value={value == null ? '' : String(value)}
              onChange={(e) => {
                const raw = e.target.value;
                if (typeof value === 'number') {
                  const next = { ...obj, [key]: raw === '' ? 0 : Number(raw) };
                  setObj(next); onChange?.(next);
                } else {
                  const next = { ...obj, [key]: raw };
                  setObj(next); onChange?.(next);
                }
              }}
              style={{ minWidth: 220 }}
            />
          )}
        </div>
      ))}
      <div className="toolbar">
        <Button size="sm" variant="outline" onClick={() => setMode('json')}>
          JSON
        </Button>
        {!readOnly ? (
          <Button variant="primary" onClick={() => void onSave(obj)}>
            {t('configure.forms.saveSection', { section })}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
