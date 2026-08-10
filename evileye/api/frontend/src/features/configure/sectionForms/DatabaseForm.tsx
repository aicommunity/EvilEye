import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { FormActions, FormField, FormGrid } from '../formLayout';
import { formatInt, INT_STEP, parseIntInput } from '../numberFormat';

type DbCfg = {
  enabled?: boolean;
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  image_dir?: string;
  [key: string]: unknown;
};

function asObj(data: unknown): DbCfg {
  return data && typeof data === 'object' && !Array.isArray(data) ? (data as DbCfg) : {};
}

export function DatabaseForm({
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
  const [obj, setObj] = useState<DbCfg>(() => asObj(data));
  useEffect(() => setObj(asObj(data)), [data]);

  const update = (next: DbCfg) => {
    setObj(next);
    onChange?.(next);
  };

  return (
    <div>
      <p className="hint">{t('configure.forms.hintDatabase')}</p>
      <FormGrid>
        <FormField label="enabled">
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.enabled)}
            onChange={(e) => update({ ...obj, enabled: e.target.checked })}
          />
        </FormField>
        <FormField label="host">
          <input disabled={readOnly} value={String(obj.host ?? '')} onChange={(e) => update({ ...obj, host: e.target.value })} />
        </FormField>
        <FormField label="port">
          <input
            type="number"
            step={INT_STEP}
            disabled={readOnly}
            value={obj.port != null ? formatInt(Number(obj.port)) : ''}
            onChange={(e) => update({ ...obj, port: parseIntInput(e.target.value) })}
          />
        </FormField>
        <FormField label="database">
          <input
            disabled={readOnly}
            value={String(obj.database ?? '')}
            onChange={(e) => update({ ...obj, database: e.target.value })}
          />
        </FormField>
        <FormField label="user">
          <input disabled={readOnly} value={String(obj.user ?? '')} onChange={(e) => update({ ...obj, user: e.target.value })} />
        </FormField>
        <FormField label="password">
          <input
            type="password"
            disabled={readOnly}
            placeholder={obj.password ? '••••••••' : ''}
            value={obj.password === '***' ? '' : String(obj.password ?? '')}
            onChange={(e) => update({ ...obj, password: e.target.value })}
            autoComplete="new-password"
          />
        </FormField>
        <FormField label="image_dir">
          <input
            disabled={readOnly}
            value={String(obj.image_dir ?? '')}
            onChange={(e) => update({ ...obj, image_dir: e.target.value })}
          />
        </FormField>
      </FormGrid>
      <FormActions>
        {!readOnly ? (
          <Button variant="primary" onClick={() => void onSave(obj)}>
            {t('configure.forms.saveSection', { section: 'database' })}
          </Button>
        ) : null}
      </FormActions>
    </div>
  );
}
