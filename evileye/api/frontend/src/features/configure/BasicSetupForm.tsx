import { useCallback, useEffect, useState } from 'react';
import {
  setupApi,
  runCreate,
  runStart,
  type BasicSetup,
  type BasicSource,
  type SetupStatus,
  ApiError,
} from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';

const SOURCE_TYPES = ['IpCamera', 'VideoFile', 'Device'] as const;

function emptyBasic(configName: string): BasicSetup {
  return {
    config_name: configName,
    data_dir: 'EvilEyeData',
    storage_mode: 'json',
    database: {
      host_name: 'localhost',
      port: 5432,
      database_name: 'evil_eye_db',
      user_name: 'postgres',
      password: '',
    },
    sources: [],
    analytics_enabled: false,
    recording_enabled: false,
  };
}

export function BasicSetupForm({
  configName,
  onStatus,
}: {
  configName: string;
  onStatus?: (s: SetupStatus) => void;
}) {
  const { t } = useI18n();
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const canEdit = hasPermission('config:edit');
  const canRun = hasPermission('runtime:control');

  const [basic, setBasic] = useState<BasicSetup>(() => emptyBasic(configName));
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dbPassword, setDbPassword] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [st, body] = await Promise.all([setupApi.status(), setupApi.basicGet(configName)]);
      setStatus(st);
      onStatus?.(st);
      setBasic({ ...body, config_name: configName });
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setLoading(false);
    }
  }, [configName, onStatus, showError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const update = (patch: Partial<BasicSetup>) => setBasic((prev) => ({ ...prev, ...patch }));

  const updateSource = (index: number, patch: Partial<BasicSource>) => {
    setBasic((prev) => {
      const sources = prev.sources.map((s, i) => (i === index ? { ...s, ...patch } : s));
      return { ...prev, sources };
    });
  };

  const addSource = () => {
    setBasic((prev) => {
      const nextId = prev.sources.reduce((m, s) => Math.max(m, s.id), -1) + 1;
      return {
        ...prev,
        sources: [
          ...prev.sources,
          {
            id: nextId,
            name: `Cam${nextId + 1}`,
            type: 'IpCamera',
            address: 'rtsp://',
            username: '',
            password: '',
            record: true,
          },
        ],
      };
    });
  };

  const removeSource = (index: number) => {
    setBasic((prev) => ({ ...prev, sources: prev.sources.filter((_, i) => i !== index) }));
  };

  const buildPayload = (): BasicSetup => ({
    ...basic,
    config_name: configName,
    database: {
      ...basic.database,
      password: dbPassword || undefined,
    },
  });

  const save = async (andRun: boolean) => {
    if (!canEdit) return;
    setSaving(true);
    try {
      const res = await setupApi.basicPut(buildPayload());
      setBasic(res.basic);
      setStatus(res.status);
      onStatus?.(res.status);
      setDbPassword('');
      showSuccess(t('setup.saved'));
      if (andRun) {
        if (!res.status.ready_to_run) {
          showError(t('setup.notReadyToRun'));
          return;
        }
        if (!canRun) {
          showError(t('setup.noRunPermission'));
          return;
        }
        const run = await runCreate({ config_name: configName });
        await runStart(run.id as number);
        showSuccess(t('setup.runStarted'));
      }
    } catch (e) {
      showError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : t('common.saveFail'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="hint">{t('configure.loading')}</p>;
  }

  return (
    <div className="basic-setup-form">
      {status?.needs_setup ? <p className="setup-banner">{t('setup.needsSetupBanner')}</p> : null}

      <h3>{t('setup.sectionDataDir')}</h3>
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
          <Button
            size="sm"
            variant="outline"
            disabled={!basic.data_dir}
            onClick={() =>
              void setupApi
                .checkDataDir(basic.data_dir)
                .then((r) => (r.ok ? showSuccess(r.message) : showError(r.message)))
                .catch((e) => showError(e.message))
            }
          >
            {t('setup.checkPath')}
          </Button>
        </div>
      </FormGrid>

      <h3>{t('setup.sectionStorage')}</h3>
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
              disabled={!canEdit}
              value={basic.database.port}
              onChange={(e) =>
                update({ database: { ...basic.database, port: Number(e.target.value) || 5432 } })
              }
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
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                void setupApi
                  .testDatabase({ ...basic.database, password: dbPassword })
                  .then((r) => (r.ok ? showSuccess(r.message) : showError(r.message)))
                  .catch((e) => showError(e.message))
              }
            >
              {t('setup.testDb')}
            </Button>
          </div>
        </FormGrid>
      ) : (
        <p className="hint">{t('setup.storageJsonHint')}</p>
      )}

      <h3>{t('setup.sectionSources')}</h3>
      <p className="hint">{t('setup.sourcesHint')}</p>
      {basic.sources.map((src, i) => (
        <div key={`${src.id}-${i}`} className="config-source-block">
          <FormGrid>
            <FormField label={t('setup.sourceName')}>
              <input
                disabled={!canEdit}
                value={src.name}
                onChange={(e) => updateSource(i, { name: e.target.value })}
              />
            </FormField>
            <FormField label={t('setup.sourceType')}>
              <select
                disabled={!canEdit}
                value={src.type}
                onChange={(e) => updateSource(i, { type: e.target.value })}
              >
                {SOURCE_TYPES.map((tp) => (
                  <option key={tp} value={tp}>
                    {tp}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label={t('setup.sourceAddress')}>
              <input
                disabled={!canEdit}
                value={String(src.address ?? '')}
                onChange={(e) => updateSource(i, { address: e.target.value })}
              />
            </FormField>
            <FormField label={t('setup.sourceUser')}>
              <input
                disabled={!canEdit}
                value={src.username ?? ''}
                onChange={(e) => updateSource(i, { username: e.target.value })}
              />
            </FormField>
            <FormField label={t('setup.sourcePassword')}>
              <input
                type="password"
                disabled={!canEdit}
                placeholder={src.password_set ? '••••••••' : ''}
                value={src.password ?? ''}
                onChange={(e) => updateSource(i, { password: e.target.value })}
                autoComplete="new-password"
              />
            </FormField>
            <FormField label={t('setup.sourceRecord')}>
              <input
                type="checkbox"
                disabled={!canEdit}
                checked={Boolean(src.record)}
                onChange={(e) => updateSource(i, { record: e.target.checked })}
              />
            </FormField>
          </FormGrid>
          {canEdit ? (
            <Button size="sm" variant="danger" onClick={() => removeSource(i)}>
              {t('setup.removeSource')}
            </Button>
          ) : null}
        </div>
      ))}
      {canEdit ? (
        <Button size="sm" variant="outline" onClick={addSource}>
          {t('setup.addSource')}
        </Button>
      ) : null}

      <h3>{t('setup.sectionOptions')}</h3>
      <FormGrid>
        <FormField label={t('setup.analytics')}>
          <input
            type="checkbox"
            disabled={!canEdit}
            checked={basic.analytics_enabled}
            onChange={(e) => update({ analytics_enabled: e.target.checked })}
          />
        </FormField>
        <FormField label={t('setup.recording')}>
          <input
            type="checkbox"
            disabled={!canEdit}
            checked={basic.recording_enabled}
            onChange={(e) => update({ recording_enabled: e.target.checked })}
          />
        </FormField>
      </FormGrid>
      <p className="hint">{t('setup.analyticsHint')}</p>

      {canEdit ? (
        <div className="modal-actions" style={{ marginTop: '1rem' }}>
          <Button variant="primary" disabled={saving} onClick={() => void save(false)}>
            {t('setup.save')}
          </Button>
          <Button variant="outline" disabled={saving} onClick={() => void save(true)}>
            {t('setup.saveAndRun')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
