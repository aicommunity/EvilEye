import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  configGet,
  configUpdate,
  configListSections,
  configGetSection,
  configPutSection,
  configValidate,
  setupApi,
  type StudioTab,
  type SetupStatus,
  ApiError,
} from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { SourcesForm } from './sectionForms/SourcesForm';
import { RecordForm } from './sectionForms/RecordForm';
import { DetectorsForm } from './sectionForms/DetectorsForm';
import { TrackersForm } from './sectionForms/TrackersForm';
import { McTrackersForm } from './sectionForms/McTrackersForm';
import { EventsDetectorsForm } from './sectionForms/EventsDetectorsForm';
import { EventsProcessorForm } from './sectionForms/EventsProcessorForm';
import { HandlerForm } from './sectionForms/HandlerForm';
import { DatabaseForm } from './sectionForms/DatabaseForm';
import { DatabaseAdaptersForm } from './sectionForms/DatabaseAdaptersForm';
import { VisualizerForm } from './sectionForms/VisualizerForm';
import { ControllerForm } from './sectionForms/ControllerForm';
import { ServerForm } from './sectionForms/ServerForm';
import { StorageMonitorForm } from './sectionForms/StorageMonitorForm';
import { GenericSectionForm } from './sectionForms/GenericSectionForm';
import { JsonAdvancedTab } from './JsonAdvancedTab';
import { ConfigHistoryPanel } from './ConfigHistoryPanel';
import { RoiCanvas } from './RoiCanvas';
import { ZoneCanvas } from './ZoneCanvas';
import { ClassMappingEditor } from './ClassMappingEditor';
import { configBasename, stableStringify, tabsFromLegacySections } from './studioTabs';
import { useI18n } from '../../i18n';
import { BasicSetupForm } from './BasicSetupForm';
import { ConfigModeToggle, useConfigUiMode } from './ConfigModeToggle';
import { readPendingApply, writePendingApply } from './pendingApply';
import { restartConfigRun } from './restartConfigRun';

export type ConfigStudioProps = {
  mode: 'current' | 'file';
  configName: string | null;
  currentBadge?: boolean;
  allowConfigHistory?: boolean;
  readOnly?: boolean;
};

export function ConfigStudio({
  mode,
  configName,
  currentBadge,
  allowConfigHistory = false,
  readOnly: readOnlyProp,
}: ConfigStudioProps) {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const canEdit = readOnlyProp === true ? false : hasPermission('config:edit');
  const canRun = hasPermission('runtime:control');

  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const { mode: uiMode, setMode: setUiMode, needsSetup } = useConfigUiMode(setupStatus);
  const [pendingApply, setPendingApply] = useState(false);
  const [applying, setApplying] = useState(false);

  const name = configName;

  const markPendingApply = useCallback(
    (pending: boolean) => {
      if (!name) return;
      writePendingApply(name, pending);
      setPendingApply(pending);
    },
    [name],
  );

  useEffect(() => {
    if (!name) {
      setSetupStatus(null);
      setPendingApply(false);
      return;
    }
    setPendingApply(readPendingApply(name));
    void setupApi
      .status(name)
      .then((s) => setSetupStatus(s))
      .catch(() => setSetupStatus(null));
  }, [name]);

  const [tabs, setTabs] = useState<StudioTab[]>([]);
  const [activeId, setActiveId] = useState('sources');
  const [sectionData, setSectionData] = useState<unknown>(null);
  const [baselineJson, setBaselineJson] = useState('');
  const [dirty, setDirty] = useState(false);
  const [fullJson, setFullJson] = useState('{}');
  const [sourceId, setSourceId] = useState(0);

  const activeTab = useMemo(() => tabs.find((t) => t.id === activeId), [tabs, activeId]);
  const activePath = activeTab?.path ?? activeId;

  const specialIds = useMemo(() => {
    const extra = ['roi', 'zones', 'classes', 'json'];
    if (allowConfigHistory) extra.push('history');
    return extra;
  }, [allowConfigHistory]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!name) {
      setTabs([]);
      setSectionData(null);
      setDirty(false);
      return;
    }
    void (async () => {
      try {
        const secs = await configListSections(name);
        const nextTabs = secs.tabs?.length ? secs.tabs : tabsFromLegacySections(secs.sections);
        setTabs(nextTabs);
        setActiveId((prev) => {
          if (nextTabs.some((t) => t.id === prev) || specialIds.includes(prev)) return prev;
          return nextTabs[0]?.id ?? 'json';
        });
        const body = await configGet(name);
        setFullJson(JSON.stringify(body, null, 2));
        setDirty(false);
      } catch (e) {
        showError(e instanceof Error ? e.message : t('common.error'));
      }
    })();
  }, [name, showError, specialIds]);

  useEffect(() => {
    if (!name || !activeId || specialIds.includes(activeId)) return;
    // Wait until studio tabs are resolved so we use pipeline.sources (etc.), not bare "sources".
    if (!tabs.length) return;
    const tab = tabs.find((t) => t.id === activeId);
    if (!tab) return;
    const path = tab.path;
    let cancelled = false;
    void configGetSection(name, path)
      .then((data) => {
        if (cancelled) return;
        setSectionData(data);
        setBaselineJson(stableStringify(data));
        setDirty(false);
      })
      .catch((e) => {
        if (cancelled) return;
        showError(e instanceof ApiError ? e.message : t('common.sectionError'));
      });
    return () => {
      cancelled = true;
    };
  }, [name, activeId, tabs, showError, specialIds, t]);

  const markDirtyFromDraft = (draft: unknown) => {
    setDirty(stableStringify(draft) !== baselineJson);
  };

  const saveSection = async (data: unknown) => {
    if (!canEdit || !name) return;
    try {
      await configPutSection(name, activePath, data);
      showSuccess(t('configure.sectionSaved'));
      setSectionData(data);
      setBaselineJson(stableStringify(data));
      setDirty(false);
      markPendingApply(true);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('configure.saveFail'));
    }
  };

  const applyRestart = async () => {
    if (!name || !canRun) return;
    setApplying(true);
    try {
      await restartConfigRun(name);
      markPendingApply(false);
      showSuccess(t('setup.runStarted'));
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setApplying(false);
    }
  };

  const switchTab = (s: string) => {
    if (dirty && !window.confirm(t('configure.dirtyConfirm'))) return;
    setActiveId(s);
    setDirty(false);
  };

  const formProps = {
    data: sectionData,
    readOnly: !canEdit,
    onSave: saveSection,
    onChange: markDirtyFromDraft,
  };

  const renderSectionForm = () => {
    switch (activeId) {
      case 'sources':
        return <SourcesForm {...formProps} />;
      case 'record':
        return <RecordForm {...formProps} />;
      case 'detectors':
        return <DetectorsForm {...formProps} />;
      case 'trackers':
        return <TrackersForm {...formProps} />;
      case 'mc_trackers':
        return <McTrackersForm {...formProps} />;
      case 'events_detectors':
      case 'events':
        return <EventsDetectorsForm {...formProps} />;
      case 'events_processor':
        return <EventsProcessorForm {...formProps} />;
      case 'objects_handler':
        return <HandlerForm {...formProps} />;
      case 'database':
        return <DatabaseForm {...formProps} />;
      case 'database_adapters':
        return <DatabaseAdaptersForm {...formProps} />;
      case 'storage_monitor':
        return <StorageMonitorForm {...formProps} />;
      case 'visualizer':
        return <VisualizerForm {...formProps} />;
      case 'controller':
        return <ControllerForm {...formProps} />;
      case 'server':
        return <ServerForm {...formProps} />;
      default:
        return <GenericSectionForm section={activeId} {...formProps} />;
    }
  };

  if (!name) {
    return (
      <section className="panel active">
        <div className="card">
          <h2>{t('configure.title')}</h2>
          <p className="empty">
            {mode === 'current'
              ? t('configure.noActiveRun')
              : t('configure.noConfig')}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel active">
      <div className="card">
        <h2>
          {t('configure.title')}{' '}
          {currentBadge || mode === 'current' ? (
            <span className="config-active-badge">{t('configure.activeConfig', { name: configBasename(name) ?? name })}</span>
          ) : (
            <span className="hint">· {name}</span>
          )}
          {dirty ? <span className="hint"> · {t('configure.dirty')}</span> : null}
        </h2>
        {pendingApply ? (
          <div className="setup-banner setup-banner--pending">
            <span>{t('setup.pendingApplyBanner')}</span>
            {canRun ? (
              <Button size="sm" variant="primary" disabled={applying} onClick={() => void applyRestart()}>
                {t('setup.saveAndRun')}
              </Button>
            ) : null}
          </div>
        ) : null}
        <div className="toolbar" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
          <ConfigModeToggle mode={uiMode} onChange={setUiMode} needsSetup={needsSetup} />
          {uiMode === 'advanced' ? (
            <Button
              variant="outline"
              onClick={() =>
                void configValidate(name)
                  .then((r) => {
                    if (r.ok) showSuccess(t('configure.valid'));
                    else showError(r.errors.join('; ') || t('configure.validationErrors'));
                  })
                  .catch((e) => showError(e.message))
              }
            >
              {t('configure.validate')}
            </Button>
          ) : null}
        </div>
        {uiMode === 'basic' ? (
          <>
            <p className="hint">{t('setup.basicHint')}</p>
            <BasicSetupForm
              configName={name}
              onStatus={setSetupStatus}
              onPendingApplyChange={markPendingApply}
            />
          </>
        ) : (
          <>
        <p className="hint">
          {mode === 'current'
            ? t('configure.hintCurrent')
            : t('configure.hintFile')}
        </p>
        <div className="journal-tabs config-studio-tabs">
          {[...tabs.map((tab) => tab.id), ...specialIds].map((s) => (
            <button
              key={s}
              type="button"
              className={`journal-tab${activeId === s ? ' active' : ''}`}
              onClick={() => switchTab(s)}
            >
              {(() => {
                const key = `studio.tab.${s}`;
                const label = t(key);
                return label === key ? s : label;
              })()}
            </button>
          ))}
        </div>
        {activeId === 'json' ? (
          <JsonAdvancedTab
            value={fullJson}
            readOnly={!canEdit}
            onSave={async (text) => {
              await configUpdate(name, JSON.parse(text));
              setFullJson(text);
              setBaselineJson(text);
              setDirty(false);
              markPendingApply(true);
              showSuccess(t('configure.jsonSaved'));
            }}
            onChange={(text) => setDirty(text !== fullJson)}
          />
        ) : activeId === 'history' ? (
          <ConfigHistoryPanel configName={name} />
        ) : activeId === 'roi' ? (
          <RoiCanvas
            configName={name}
            sourceId={sourceId}
            onSourceIdChange={setSourceId}
            readOnly={!canEdit}
            onSaved={(restartRequired) => {
              if (restartRequired) markPendingApply(true);
            }}
          />
        ) : activeId === 'zones' ? (
          <ZoneCanvas
            configName={name}
            sourceId={sourceId}
            onSourceIdChange={setSourceId}
            readOnly={!canEdit}
            onSaved={(restartRequired) => {
              if (restartRequired) markPendingApply(true);
            }}
          />
        ) : activeId === 'classes' ? (
          <ClassMappingEditor
            configName={name}
            readOnly={!canEdit}
            onSaved={(restartRequired) => {
              if (restartRequired) markPendingApply(true);
            }}
          />
        ) : (
          renderSectionForm()
        )}
          </>
        )}
      </div>
    </section>
  );
}
