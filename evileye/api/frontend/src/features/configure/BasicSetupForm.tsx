import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  setupApi,
  configGet,
  configPutSection,
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
import { restartConfigRun } from './restartConfigRun';
import { SourceAdvancedEditor } from './SourceAdvancedEditor';
import { cloneSourceRow, collectOccupiedSourceIds, findSourceRowIndex } from './sourceRowUtils';

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
  onPendingApplyChange,
}: {
  configName: string;
  onStatus?: (s: SetupStatus) => void;
  onPendingApplyChange?: (pending: boolean) => void;
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
  const [advancedOpen, setAdvancedOpen] = useState<{
    index: number;
    row: Record<string, unknown>;
    occupiedIds: number[];
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [st, body] = await Promise.all([setupApi.status(configName), setupApi.basicGet(configName)]);
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

  const recordingSummary = useMemo(() => {
    const recording = basic.sources.filter((s) => Boolean(s.record));
    if (!recording.length) return t('setup.recordingSummaryOff');
    const names = recording.map((s) => s.name || `Cam${s.id + 1}`).join(', ');
    return t('setup.recordingSummaryOn', { names, count: recording.length });
  }, [basic.sources, t]);

  const buildPayload = (): BasicSetup => {
    const sources = basic.sources;
    return {
      ...basic,
      config_name: configName,
      recording_enabled: sources.some((s) => Boolean(s.record)),
      database: {
        ...basic.database,
        password: dbPassword || undefined,
      },
    };
  };

  const save = async () => {
    if (!canEdit) return;
    setSaving(true);
    try {
      const res = await setupApi.basicPut(buildPayload());
      setBasic(res.basic);
      setStatus(res.status);
      onStatus?.(res.status);
      setDbPassword('');
      showSuccess(t('setup.saved'));
      onPendingApplyChange?.(true);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : t('common.saveFail'));
    } finally {
      setSaving(false);
    }
  };

  const restart = async () => {
    if (!canRun) return;
    setSaving(true);
    try {
      if (status && !status.ready_to_run) {
        showError(t('setup.notReadyToRun'));
        return;
      }
      // pendingApply cleared inside restartConfigRun before the request.
      onPendingApplyChange?.(false);
      const res = await restartConfigRun(configName);
      onPendingApplyChange?.(false);
      showSuccess(res.scheduled ? t('setup.restartScheduled') : t('setup.runStarted'));
    } catch (e) {
      showError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  const openAdvanced = async (index: number) => {
    try {
      const full = await configGet(configName);
      const pipeline = (full.pipeline ?? {}) as Record<string, unknown>;
      const sources = Array.isArray(pipeline.sources) ? (pipeline.sources as Record<string, unknown>[]) : [];
      const basicSrc = basic.sources[index];
      const si = findSourceRowIndex(sources, basicSrc?.id ?? index, index);
      if (si < 0 || !sources[si]) {
        showError(t('common.loadFail'));
        return;
      }
      setAdvancedOpen({
        index: si,
        row: cloneSourceRow(sources[si]),
        occupiedIds: [...collectOccupiedSourceIds(sources, si)],
      });
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.loadFail'));
    }
  };

  const applyAdvanced = async (row: Record<string, unknown>) => {
    if (advancedOpen == null) return;
    const full = await configGet(configName);
    const pipeline = (full.pipeline ?? {}) as Record<string, unknown>;
    const sources = Array.isArray(pipeline.sources)
      ? (pipeline.sources as Record<string, unknown>[]).map((r) => cloneSourceRow(r))
      : [];
    if (advancedOpen.index < 0 || advancedOpen.index >= sources.length) {
      throw new Error(t('common.saveFail'));
    }
    sources[advancedOpen.index] = row;
    await configPutSection(configName, 'pipeline.sources', sources);
    onPendingApplyChange?.(true);
    const splitTouched =
      Boolean(row.split) ||
      Boolean((advancedOpen.row as { split?: boolean }).split) ||
      (Array.isArray(row.source_ids) && row.source_ids.length > 1);
    showSuccess(splitTouched ? t('setup.splitRestartHint') : t('setup.saved'));
    setAdvancedOpen(null);
    await load();
  };

  const cameraTitle = (src: BasicSource, index: number) => {
    const base = src.name || `Cam${src.id + 1}`;
    const extras = (src.extra_names || []).filter(Boolean);
    const name = extras.length ? `${base} (+${extras.join(', ')})` : base;
    return t('setup.cameraCardTitle', { index: index + 1, name });
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
      <div className="basic-sources-list">
        {basic.sources.map((src, i) => (
          <div key={`${src.id}-${i}`} className="basic-source-card">
            <div className="basic-source-card__title">{cameraTitle(src, i)}</div>
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
              <div className="basic-source-card__actions">
                <Button size="sm" variant="outline" onClick={() => void openAdvanced(i)}>
                  {t('setup.sourceAdvanced')}
                </Button>
                <Button size="sm" variant="danger" onClick={() => removeSource(i)}>
                  {t('setup.removeSource')}
                </Button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {canEdit ? (
        <div className="basic-add-source-bar">
          <Button size="sm" variant="success" onClick={addSource}>
            {t('setup.addSource')}
          </Button>
        </div>
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
      </FormGrid>
      <p className="hint">{t('setup.analyticsHint')}</p>
      <p className="basic-recording-summary">{recordingSummary}</p>

      {canEdit || canRun ? (
        <div className="modal-actions" style={{ marginTop: '1rem' }}>
          {canEdit ? (
            <Button variant="primary" disabled={saving} onClick={() => void save()}>
              {t('setup.save')}
            </Button>
          ) : null}
          {canRun ? (
            <Button variant="outline" disabled={saving} onClick={() => void restart()}>
              {t('setup.restart')}
            </Button>
          ) : null}
        </div>
      ) : null}

      <SourceAdvancedEditor
        open={Boolean(advancedOpen)}
        configName={configName}
        sourceIndex={advancedOpen?.index ?? 0}
        initialRow={advancedOpen?.row ?? {}}
        occupiedIds={advancedOpen?.occupiedIds}
        readOnly={!canEdit}
        onClose={() => setAdvancedOpen(null)}
        onApplied={applyAdvanced}
      />
    </div>
  );
}
