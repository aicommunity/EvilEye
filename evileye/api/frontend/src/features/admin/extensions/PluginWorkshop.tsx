import { useEffect, useRef, useState } from 'react';
import {
  type ExtensionCatalog,
  type ExtensionModule,
  type PluginOperation,
  extensionsApi,
} from '../../../api';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { Field } from './shared';

function isRecentOperationFailure(operation: PluginOperation): boolean {
  return operation.status === 'failed'
    && typeof operation.updated_at === 'number'
    && Date.now() / 1000 - operation.updated_at < 30;
}

function operationStatusLabel(operation: PluginOperation): string {
  return isRecentOperationFailure(operation) ? 'builder.status.settling' : `builder.status.${operation.status}`;
}

export function PluginWorkshop({ catalog, onPluginReady }: { catalog: ExtensionCatalog; onPluginReady: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [pluginStateNote, setPluginStateNote] = useState('');
  const [template, setTemplate] = useState(catalog.templates[0]?.id || 'processor');
  const [operation, setOperation] = useState<PluginOperation | null>(null);
  const [recentOperations, setRecentOperations] = useState<PluginOperation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollingFailed, setPollingFailed] = useState(false);
  const refreshedOperations = useRef(new Set<string>());
  useEffect(() => {
    void extensionsApi.operations().then((items) => {
      setRecentOperations(items);
      if (items.length) setOperation(items[0]);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);
  useEffect(() => {
    if (!operation || ['completed', 'pending_restart', 'dependencies_missing'].includes(operation.status)) return;
    // The API process can be stopped while the detached installer is restarting
    // it. During that handoff the request handler may briefly report failure;
    // keep checking for a short window in case the worker records completion.
    const recentDispatchFailure = operation.status === 'failed'
      && typeof operation.updated_at === 'number'
      && Date.now() / 1000 - operation.updated_at < 30;
    if (operation.status === 'failed' && !recentDispatchFailure) return;
    const timer = window.setInterval(() => {
      void extensionsApi.operation(operation.id).then((next) => {
        setOperation(next);
        setRecentOperations((items) => [next, ...items.filter((item) => item.id !== next.id)].slice(0, 20));
        setPollingFailed(false);
      }).catch(() => {
        // Restarting the Web backend briefly interrupts status requests. Keep
        // polling and do not present this transport error as an install failure.
        setPollingFailed(true);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [operation]);

  useEffect(() => {
    if (operation?.status !== 'completed' || refreshedOperations.current.has(operation.id)) return;
    refreshedOperations.current.add(operation.id);
    onPluginReady();
  }, [operation, onPluginReady]);

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const created = await extensionsApi.createPlugin(name, template, password);
      setPassword('');
      setOperation(created);
      setRecentOperations((items) => [created, ...items.filter((item) => item.id !== created.id)].slice(0, 20));
      setPollingFailed(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const toggleDisabled = async (pluginName: string, disabled: boolean) => {
    setError('');
    try {
      await extensionsApi.setPluginDisabled(pluginName, disabled);
      setPluginStateNote(t(disabled ? 'builder.pluginDisabledNote' : 'builder.pluginEnabledNote', { name: pluginName }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  const pluginStatus = catalog.plugin_status;
  return <div className="extension-builder-content">
    <p className="hint">{t('builder.pluginHint')}</p>
    {pluginStatus && (pluginStatus.failed.length || pluginStatus.disabled.length) ? <section className="extension-panel" aria-label={t('builder.pluginProblems')}>
      <div className="extension-section-heading"><h3>{t('builder.pluginProblems')}</h3></div>
      <ul className="extension-installed-list">
        {pluginStatus.failed.map((item) => <li key={`failed-${item.name}`}>
          <strong>{item.name}</strong><span className="extension-error">{t('builder.pluginFailed')}</span>
          <small>{item.reason}</small>
          <Button onClick={() => void toggleDisabled(item.name, true)}>{t('builder.pluginDisable')}</Button>
        </li>)}
        {pluginStatus.disabled.map((pluginName) => <li key={`disabled-${pluginName}`}>
          <strong>{pluginName}</strong><span>{t('builder.pluginDisabled')}</span>
          {pluginStatus.disabled_by_env.includes(pluginName) && !pluginStatus.disabled_in_ui.includes(pluginName)
            ? <small>{t('builder.pluginDisabledByEnv')}</small>
            : <Button onClick={() => void toggleDisabled(pluginName, false)}>{t('builder.pluginEnable')}</Button>}
        </li>)}
      </ul>
      {pluginStateNote ? <p className="hint" role="status">{pluginStateNote}</p> : null}
    </section> : null}
    <section className="extension-panel">
      <div className="extension-section-heading">
        <h3>{t('builder.installedExtensions', { count: catalog.modules.filter((module) => module.plugin_id !== 'evileye').length + catalog.pipelines.filter((pipeline) => pipeline.plugin_id !== 'evileye').length })}</h3>
      </div>
      {catalog.modules.some((module) => module.plugin_id !== 'evileye') || catalog.pipelines.some((pipeline) => pipeline.plugin_id !== 'evileye') ? <ul className="extension-installed-list">
        {catalog.modules.filter((module) => module.plugin_id !== 'evileye').map((module) => <li key={module.id}>
          <strong>{module.display_name}</strong> <code>{module.id}</code><span>{t(`builder.moduleKind.${module.kind}`)}</span>
          <small>{t('builder.modulePlacement', { placement: modulePlacement(module, t) })}</small>
        </li>)}
        {catalog.pipelines.filter((pipeline) => pipeline.plugin_id !== 'evileye').map((pipeline) => <li key={pipeline.id}>
          <strong>{pipeline.display_name}</strong> <code>{pipeline.config_id}</code><span>{t('builder.moduleKind.pipeline')}</span>
          <small>{t('builder.pipelinePlacement')}</small>
        </li>)}
      </ul> : <p className="hint">{t('builder.noInstalledExtensions')}</p>}
    </section>
    <div className="extension-panel">
      <div className="extension-form-grid">
        <Field label={t('builder.pluginName')} hint={t('builder.pluginNameHint')}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="site-safety" autoComplete="off" />
        </Field>
        <Field label={t('builder.confirmPassword')} hint={t('builder.confirmPasswordHint')}>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </Field>
        <Field label={t('builder.template')}>
          <select value={template} onChange={(event) => setTemplate(event.target.value)}>
            {catalog.templates.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.module_id}</option>)}
          </select>
        </Field>
      </div>
      {catalog.templates.find((item) => item.id === template)?.description ? <p className="hint">{catalog.templates.find((item) => item.id === template)?.description}</p> : null}
      <Button variant="primary" onClick={() => void create()} disabled={busy || !name.trim() || !password}>{busy ? t('builder.creating') : t('builder.createInstall')}</Button>
      {error ? <p className="extension-error">{error}</p> : null}
    </div>
    {pollingFailed ? <p className="extension-warning" role="status" aria-live="polite">{t('builder.operationReconnectWarning')}</p> : null}
    {recentOperations.length ? <section className="extension-panel extension-recent-operations">
      <h3>{t('builder.recentOperations')}</h3>
      <div className="toolbar">
            {recentOperations.map((item) => <Button key={item.id} variant={item.id === operation?.id ? 'primary' : 'outline'} onClick={() => setOperation(item)}>
              {item.name} · {t(operationStatusLabel(item))}
        </Button>)}
      </div>
    </section> : null}
    {operation ? <section className="extension-panel">
      <div className="extension-section-heading"><h3>{t('builder.operation')}</h3><span className={`extension-operation-state ${isRecentOperationFailure(operation) ? 'state-settling' : `state-${operation.status}`}`}>{t(operationStatusLabel(operation))}</span></div>
      <p>{isRecentOperationFailure(operation) ? t('builder.operationSettlingHint') : operation.message}</p>
      <dl className="extension-operation-details"><dt>{t('builder.pluginId')}</dt><dd><code>{operation.plugin_id}</code></dd>
        <dt>{t('builder.directory')}</dt><dd><code>{operation.directory}</code></dd>
      </dl>
      {operation.missing_dependencies?.length ? <p className="extension-warning">{t('builder.missingDependencies')}: {operation.missing_dependencies.join(', ')}</p> : null}
      {operation.archive ? <Button onClick={() => void extensionsApi.downloadArchive(operation.id, `evileye-plugin-${operation.name}.zip`)}>{t('builder.downloadZip')}</Button> : null}
      {operation.status === 'pending_restart' ? <p className="hint">{t('builder.pendingRestartHint')}</p> : null}
    </section> : null}
  </div>;
}

function modulePlacement(module: ExtensionModule, translate: (key: string) => string): string {
  if (module.kind === 'event_detector' || module.kind === 'alarm_detector') return translate('builder.placement.events');
  if (module.kind === 'source') return translate('builder.placement.sources');
  if (module.kind === 'batch_processor') return translate('builder.placement.mc_trackers');
  const stageLabels: Record<string, string> = {
    preprocessors: 'builder.placement.preprocessors',
    detectors: 'builder.placement.detectors',
    trackers: 'builder.placement.trackers',
    mc_trackers: 'builder.placement.mc_trackers',
    attributes_roi: 'builder.placement.attributes_roi',
    attributes_classifier: 'builder.placement.attributes_classifier',
  };
  if (module.stages.length) return module.stages.map((stage) => stageLabels[stage] ? translate(stageLabels[stage]) : stage).join(', ');
  return translate('builder.placement.processor');
}
