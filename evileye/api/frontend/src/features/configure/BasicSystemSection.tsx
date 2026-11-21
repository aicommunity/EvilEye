import type { BasicSetup } from '../../api/setup';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';
import { formatInt, INT_STEP, parseIntInput } from './numberFormat';

export function BasicSystemSection({
  basic,
  canEdit,
  dbPassword,
  setDbPassword,
  update,
  onCheckDataDir,
  onTestDb,
}: {
  basic: BasicSetup;
  canEdit: boolean;
  dbPassword: string;
  setDbPassword: (v: string) => void;
  update: (patch: Partial<BasicSetup>) => void;
  onCheckDataDir: () => void;
  onTestDb: () => void;
}) {
  const { t } = useI18n();

  return (
    <>
      <h4 className="basic-setup-subtitle">{t('setup.sectionDataDir')}</h4>
      <FormGrid>
        <FormField label={t('setup.dataDir')}>
          <input
            disabled={!canEdit}
            value={basic.data_dir}
            onChange={(e) => update({ data_dir: e.target.value })}
            placeholder="EvilEyeData"
          />
        </FormField>
        <div className="form-actions-inline">
          <Button size="sm" variant="outline" disabled={!basic.data_dir} onClick={onCheckDataDir}>
            {t('setup.checkPath')}
          </Button>
        </div>
      </FormGrid>

      <h4 className="basic-setup-subtitle">{t('setup.sectionStorage')}</h4>
      <FormGrid>
        <FormField label={t('setup.storageMode')}>
          <select
            disabled={!canEdit}
            value={basic.storage_mode}
            onChange={(e) => update({ storage_mode: e.target.value === 'database' ? 'database' : 'json' })}
          >
            <option value="json">{t('setup.storageJson')}</option>
            <option value="database">{t('setup.storageDb')}</option>
          </select>
        </FormField>
      </FormGrid>
      {basic.storage_mode === 'database' ? (
        <FormGrid>
          <FormField label={t('setup.dbHost')}>
            <input
              disabled={!canEdit}
              value={basic.database.host_name}
              onChange={(e) => update({ database: { ...basic.database, host_name: e.target.value } })}
            />
          </FormField>
          <FormField label={t('setup.dbPort')}>
            <input
              type="number"
              step={INT_STEP}
              disabled={!canEdit}
              value={formatInt(Number(basic.database.port))}
              onChange={(e) => {
                const n = parseIntInput(e.target.value);
                update({ database: { ...basic.database, port: n ?? 5432 } });
              }}
            />
          </FormField>
          <FormField label={t('setup.dbName')}>
            <input
              disabled={!canEdit}
              value={basic.database.database_name}
              onChange={(e) => update({ database: { ...basic.database, database_name: e.target.value } })}
            />
          </FormField>
          <FormField label={t('setup.dbUser')}>
            <input
              disabled={!canEdit}
              value={basic.database.user_name}
              onChange={(e) => update({ database: { ...basic.database, user_name: e.target.value } })}
            />
          </FormField>
          <FormField label={t('setup.dbPassword')}>
            <input
              type="password"
              disabled={!canEdit}
              placeholder={basic.database.password_set ? '••••••••' : ''}
              value={dbPassword}
              onChange={(e) => setDbPassword(e.target.value)}
              autoComplete="new-password"
            />
          </FormField>
          <div className="form-actions-inline">
            <Button size="sm" variant="outline" onClick={onTestDb}>
              {t('setup.testDb')}
            </Button>
          </div>
        </FormGrid>
      ) : (
        <p className="hint">{t('setup.storageJsonHint')}</p>
      )}
    </>
  );
}
