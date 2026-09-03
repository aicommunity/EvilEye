import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  setupApi,
  configGet,
  configPutSection,
  type BasicSetup,
  type BasicSource,
  type BasicAlarmCamera,
  type SetupStatus,
  ApiError,
} from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { restartConfigRun } from './restartConfigRun';
import { SourceAdvancedEditor } from './SourceAdvancedEditor';
import { cloneSourceRow, collectOccupiedSourceIds, findSourceRowIndex } from './sourceRowUtils';
import { deriveAlarmCameras, withDerivedAlarmCameras } from './alarmCameras';
import { listCamerasFromConfig, type ConfigCameraOption } from './cameraList';
import { BasicSetupSection } from './BasicSetupSection';
import { useBasicSetupSections } from './useBasicSetupSections';
import {
  alarmSummary,
  analyticsSummary,
  recordingSummary as buildRecordingSummary,
  sourcesSummary,
  systemSummary,
} from './basicSetupSummaries';
import { BasicSystemSection } from './BasicSystemSection';
import { BasicSourcesSection } from './BasicSourcesSection';
import { BasicAnalyticsSection } from './BasicAnalyticsSection';
import { BasicAlarmScheduleSection } from './BasicAlarmScheduleSection';
import { AlarmCameraScheduleModal } from './AlarmCameraScheduleModal';

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
    alarm_schedule: {
      enabled: false,
      weekdays: [0, 1, 2, 3, 4, 5, 6],
      periods: [['22:00:00', '06:00:00']],
      class_ids: [],
      camera_cooldown_sec: 0,
    },
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
  const { t, lang } = useI18n();
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const canEdit = hasPermission('config:edit');
  const canRun = hasPermission('runtime:control');

  const [basic, setBasic] = useState<BasicSetup>(() => emptyBasic(configName));
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dbPassword, setDbPassword] = useState('');
  const [alarmModalCameraId, setAlarmModalCameraId] = useState<number | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState<{
    index: number;
    row: Record<string, unknown>;
    occupiedIds: number[];
  } | null>(null);
  const [pipelineCameras, setPipelineCameras] = useState<ConfigCameraOption[]>([]);
  const [dirty, setDirty] = useState(false);
  const hasLoadedRef = useRef(false);

  const sectionDefaults = useMemo(
    () => ({
      system: Boolean(status?.needs_setup || !status?.data_dir_confirmed),
      sources: basic.sources.length === 0,
      analytics: false,
      alarm: false,
    }),
    [status?.needs_setup, status?.data_dir_confirmed, basic.sources.length],
  );

  const { isOpen, setOpen } = useBasicSetupSections(configName, sectionDefaults);

  const load = useCallback(async () => {
    if (!hasLoadedRef.current) setLoading(true);
    try {
      const [st, body, full] = await Promise.all([
        setupApi.status(configName),
        setupApi.basicGet(configName),
        configGet(configName).catch(() => null),
      ]);
      const fromPipeline = full ? listCamerasFromConfig(full) : [];
      setPipelineCameras(fromPipeline);
      setStatus(st);
      onStatus?.(st);
      setBasic(withDerivedAlarmCameras({ ...body, config_name: configName }, fromPipeline));
      setDirty(false);
      hasLoadedRef.current = true;
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setLoading(false);
    }
  }, [configName, onStatus, showError, t]);

  useEffect(() => {
    hasLoadedRef.current = false;
  }, [configName]);

  useEffect(() => {
    void load();
  }, [load]);

  const update = (patch: Partial<BasicSetup>) => {
    setDirty(true);
    setBasic((prev) => ({ ...prev, ...patch }));
  };

  const updateSource = (index: number, patch: Partial<BasicSource>) => {
    setDirty(true);
    setBasic((prev) => {
      const sources = prev.sources.map((s, i) => (i === index ? { ...s, ...patch } : s));
      return { ...prev, sources };
    });
  };

  const updateAlarmCamera = (cameraId: number, patch: Partial<BasicAlarmCamera>) => {
    setDirty(true);
    setBasic((prev) => {
      const cameras = deriveAlarmCameras(
        prev.sources,
        prev.alarm_schedule,
        prev.alarm_cameras,
        pipelineCameras,
      );
      return {
        ...prev,
        alarm_cameras: cameras.map((c) => (c.id === cameraId ? { ...c, ...patch } : c)),
      };
    });
  };

  const addSource = () => {
    setDirty(true);
    setBasic((prev) => {
      const nextId = prev.sources.reduce((m, s) => Math.max(m, s.id), -1) + 1;
      const alarmOn = Boolean(prev.alarm_schedule?.enabled);
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
            logical_ids: [nextId],
          },
        ],
        alarm_cameras: [
          ...(prev.alarm_cameras ?? []),
          { id: nextId, name: `Cam${nextId + 1}`, alarm_enabled: alarmOn },
        ],
      };
    });
  };

  const removeSource = (index: number) => {
    setDirty(true);
    setBasic((prev) => {
      const row = prev.sources[index];
      const dropIds = new Set(row?.logical_ids?.length ? row.logical_ids : row ? [row.id] : []);
      return {
        ...prev,
        sources: prev.sources.filter((_, i) => i !== index),
        alarm_cameras: (prev.alarm_cameras ?? []).filter((c) => !dropIds.has(c.id)),
      };
    });
  };

  const recordingSummary = useMemo(
    () => buildRecordingSummary(basic.sources, t),
    [basic.sources, lang, t],
  );

  const alarmCameras = useMemo(
    () => deriveAlarmCameras(basic.sources, basic.alarm_schedule, basic.alarm_cameras, pipelineCameras),
    [basic.sources, basic.alarm_schedule, basic.alarm_cameras, pipelineCameras],
  );

  const summaries = useMemo(
    () => ({
      system: systemSummary(basic, status, t),
      sources: sourcesSummary(basic.sources, pipelineCameras, t),
      analytics: analyticsSummary(basic, recordingSummary, t),
      alarm: alarmSummary(basic.alarm_schedule, alarmCameras, basic.analytics_enabled, t),
    }),
    [basic, status, pipelineCameras, recordingSummary, alarmCameras, t],
  );

  const alarmSchedule = basic.alarm_schedule ?? emptyBasic(configName).alarm_schedule!;
  const analyticsOn = basic.analytics_enabled;

  const buildPayload = (): BasicSetup => {
    const sources = basic.sources;
    return withDerivedAlarmCameras(
      {
        ...basic,
        config_name: configName,
        recording_enabled: sources.some((s) => Boolean(s.record)),
        database: {
          ...basic.database,
          password: dbPassword || undefined,
        },
      },
      pipelineCameras,
    );
  };

  const save = async (): Promise<boolean> => {
    if (!canEdit) return true;
    setSaving(true);
    try {
      const res = await setupApi.basicPut(buildPayload());
      setBasic(res.basic);
      setStatus(res.status);
      onStatus?.(res.status);
      setDbPassword('');
      setDirty(false);
      showSuccess(t('setup.saved'));
      onPendingApplyChange?.(true);
      return true;
    } catch (e) {
      showError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : t('common.saveFail'));
      return false;
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
      if (canEdit && (dirty || Boolean(dbPassword))) {
        const saved = await save();
        if (!saved) return;
      }
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

  const modalCamera = alarmCameras.find((c) => c.id === alarmModalCameraId) ?? null;

  return (
    <div className="basic-setup-form">
      {status?.needs_setup ? <p className="setup-banner">{t('setup.needsSetupBanner')}</p> : null}

      <BasicSetupSection
        id="system"
        title={t('setup.sectionSystem')}
        summary={summaries.system}
        open={isOpen('system')}
        onOpenChange={(open) => setOpen('system', open)}
      >
        <BasicSystemSection
          basic={basic}
          canEdit={canEdit}
          dbPassword={dbPassword}
          setDbPassword={setDbPassword}
          update={update}
          onCheckDataDir={() =>
            void setupApi
              .checkDataDir(basic.data_dir)
              .then((r) => (r.ok ? showSuccess(r.message) : showError(r.message)))
              .catch((e) => showError(e instanceof Error ? e.message : String(e)))
          }
          onTestDb={() =>
            void setupApi
              .testDatabase({ ...basic.database, password: dbPassword })
              .then((r) => (r.ok ? showSuccess(r.message) : showError(r.message)))
              .catch((e) => showError(e instanceof Error ? e.message : String(e)))
          }
        />
      </BasicSetupSection>

      <BasicSetupSection
        id="sources"
        title={t('setup.sectionSources')}
        summary={summaries.sources}
        open={isOpen('sources')}
        onOpenChange={(open) => setOpen('sources', open)}
      >
        <BasicSourcesSection
          sources={basic.sources}
          canEdit={canEdit}
          cameraTitle={cameraTitle}
          onUpdateSource={updateSource}
          onAdd={addSource}
          onRemove={removeSource}
          onAdvanced={openAdvanced}
        />
      </BasicSetupSection>

      <BasicSetupSection
        id="analytics"
        title={t('setup.sectionAnalytics')}
        summary={summaries.analytics}
        open={isOpen('analytics')}
        onOpenChange={(open) => setOpen('analytics', open)}
      >
        <BasicAnalyticsSection
          analyticsEnabled={basic.analytics_enabled}
          recordingSummary={recordingSummary}
          canEdit={canEdit}
          onChange={(enabled) => update({ analytics_enabled: enabled })}
        />
      </BasicSetupSection>

      <BasicSetupSection
        id="alarm"
        title={t('scheduleAlarm.basicTitle')}
        summary={summaries.alarm}
        open={isOpen('alarm')}
        onOpenChange={(open) => setOpen('alarm', open)}
        disabled={!analyticsOn}
        disabledHint={t('setup.requiresAnalytics')}
      >
        <BasicAlarmScheduleSection
          canEdit={canEdit}
          analyticsDisabled={!analyticsOn}
          alarmSchedule={alarmSchedule}
          alarmCameras={alarmCameras}
          onUpdateSchedule={(patch) =>
            update({ alarm_schedule: { ...alarmSchedule, ...patch } })
          }
          onUpdateCamera={updateAlarmCamera}
          onOpenCameraModal={setAlarmModalCameraId}
        />
      </BasicSetupSection>

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

      <AlarmCameraScheduleModal
        open={alarmModalCameraId != null}
        camera={modalCamera}
        defaultSchedule={alarmSchedule}
        canEdit={canEdit && analyticsOn}
        onClose={() => setAlarmModalCameraId(null)}
        onApply={updateAlarmCamera}
      />
    </div>
  );
}
