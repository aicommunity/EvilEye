import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  type ExtensionCatalog,
  type PipelinePreview,
  configGet,
  configsList,
  extensionsApi,
} from '../../api';
import { Button } from '../../components/ui';
import { PageHeader } from '../../components/ui/PageHeader';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { OpaqueConfigEditor } from './extensions/DeclarativeEditor';
import { PipelineEditor, TopologyView } from './extensions/PipelineEditor';
import { PluginWorkshop } from './extensions/PluginWorkshop';
import { type BuilderTab, Field, type JsonObject, jsonDiff, newConfig, pipelineOf } from './extensions/shared';

export { ModuleListEditor } from './extensions/ModuleListEditor';
export { DeclarativeEditor } from './extensions/DeclarativeEditor';

export function ExtensionsPage() {
  const { authEnabled, user } = useAuth();
  const { t } = useI18n();
  const [catalog, setCatalog] = useState<ExtensionCatalog | null>(null);
  const [configNames, setConfigNames] = useState<string[]>([]);
  const [selectedConfig, setSelectedConfig] = useState('__new__');
  const [newName, setNewName] = useState('pipeline.json');
  const [pipelineId, setPipelineId] = useState('');
  const [config, setConfig] = useState<JsonObject>({});
  const [original, setOriginal] = useState<JsonObject>({});
  const [tab, setTab] = useState<BuilderTab>('pipeline');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [review, setReview] = useState(false);
  const [preview, setPreview] = useState<PipelinePreview | null>(null);
  const [catalogRefreshing, setCatalogRefreshing] = useState(false);
  const pipeline = useMemo(() => catalog?.pipelines.find((item) => item.config_id === pipelineId) || null, [catalog, pipelineId]);

  const refreshCatalog = useCallback(async () => {
    setCatalogRefreshing(true);
    try {
      setCatalog(await extensionsApi.catalog());
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCatalogRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!authEnabled || user?.role !== 'admin') return;
    setBusy(true);
    void Promise.all([extensionsApi.catalog(), configsList()]).then(([nextCatalog, names]) => {
      setCatalog(nextCatalog);
      setConfigNames(names);
      const initial = nextCatalog.pipelines.find((item) => item.pipeline_id === 'PipelineSurveillance') || nextCatalog.pipelines[0];
      if (initial) {
        setPipelineId(initial.config_id);
        const initialConfig = newConfig(initial);
        setConfig(initialConfig);
        setOriginal(initialConfig);
      }
    }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason))).finally(() => setBusy(false));
  }, [authEnabled, user?.role]);

  const selectConfig = async (name: string) => {
    setSelectedConfig(name);
    setReview(false);
    setError('');
    if (name === '__new__') {
      if (!catalog) return;
      const spec = catalog.pipelines.find((item) => item.config_id === pipelineId) || catalog.pipelines[0];
      if (spec) {
        const initial = newConfig(spec);
        setConfig(initial);
        setOriginal(initial);
        setNewName('pipeline.json');
      }
      return;
    }
    setBusy(true);
    try {
      const loaded = await configGet(name);
      setConfig(loaded);
      setOriginal(loaded);
      setNewName(name);
      const currentId = String(pipelineOf(loaded).pipeline_class || 'PipelineSurveillance');
      const match = catalog?.pipelines.find((item) => item.config_id === currentId || item.id === currentId);
      setPipelineId(match?.config_id || currentId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const requestReview = async () => {
    setError('');
    setNotice('');
    try {
      const checked = await extensionsApi.preview(config);
      setPreview(checked);
      if (!checked.valid) {
        setError(checked.errors.join('\n'));
        return;
      }
      setReview(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const save = async () => {
    const name = selectedConfig === '__new__' ? newName : selectedConfig;
    if (!name.trim()) return setError(t('builder.configNameRequired'));
    setBusy(true);
    setError('');
    try {
      const result = await extensionsApi.saveConfig(name, config, selectedConfig === '__new__');
      const normalized = result.name;
      const names = await configsList();
      setConfigNames(names);
      setSelectedConfig(normalized);
      setNewName(normalized);
      setOriginal(config);
      setReview(false);
      setNotice(result.backup ? t('builder.savedWithBackup', { backup: result.backup }) : t('builder.saved', { name: normalized }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  if (!authEnabled || user?.role !== 'admin') return <div className="layout"><section className="card"><h2>{t('builder.adminOnly')}</h2><p className="hint">{t('builder.adminOnlyHint')}</p></section></div>;
  if (busy && !catalog) return <div className="layout"><p className="hint">{t('common.loading')}</p></div>;
  if (!catalog) return <div className="layout"><section className="card"><h2>{t('builder.title')}</h2><p className="extension-error">{error || t('builder.catalogFailed')}</p></section></div>;
  const changes = jsonDiff(original, config);

  return <div className="layout extensions-page">
    <PageHeader title={t('builder.title')} description={t('builder.hint')} />
    <div className="config-studio-tabs">
      <button className={`tab ${tab === 'pipeline' ? 'active' : ''}`} onClick={() => setTab('pipeline')}>{t('builder.pipelineTab')}</button>
      <button className={`tab ${tab === 'plugins' ? 'active' : ''}`} onClick={() => setTab('plugins')}>{t('builder.pluginsTab')}</button>
    </div>
    {error ? <div className="extension-alert extension-alert-error">{error}</div> : null}
    {notice ? <div className="extension-alert extension-alert-success">{notice}</div> : null}

    {tab === 'pipeline' ? <>
      <div className="extension-catalog-toolbar">
        <p className="hint">{t('builder.moduleCatalogHint')}</p>
        <Button onClick={() => void refreshCatalog()} disabled={catalogRefreshing}>{catalogRefreshing ? t('builder.refreshingCatalog') : t('builder.refreshCatalog')}</Button>
      </div>
      <section className="extension-panel">
        <div className="extension-config-header">
          <Field label={t('builder.configToEdit')}>
            <select value={selectedConfig} onChange={(event) => void selectConfig(event.target.value)}>
              <option value="__new__">{t('builder.createConfig')}</option>
              {configNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </Field>
          {selectedConfig === '__new__' ? <Field label={t('builder.configName')}>
            <input value={newName} onChange={(event) => setNewName(event.target.value)} />
          </Field> : null}
        </div>
        {pipeline ? <PipelineEditor config={config} setConfig={(next) => { setConfig(next); setPreview(null); }} catalog={catalog} pipeline={pipeline} onPipelineChange={setPipelineId} /> : (
          <OpaqueConfigEditor config={config} pipelineId={String(pipelineOf(config).pipeline_class || pipelineId)} catalog={catalog}
            onConfig={(next) => { setConfig(next); setPreview(null); }} onPipeline={setPipelineId} />
        )}
        <div className="toolbar extension-save-toolbar">
          <Button variant="primary" onClick={() => void requestReview()} disabled={busy}>{t('builder.reviewSave')}</Button>
          <span className="hint">{t('builder.saveHint')}</span>
        </div>
      </section>
      {review ? <section className="extension-panel extension-review" aria-live="polite">
        <h3>{t('builder.reviewTitle')}</h3>
        <p className="hint">{t('builder.reviewHint')}</p>
        {preview ? <TopologyView preview={preview} /> : null}
        {changes.length ? <ul className="extension-diff">{changes.map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}</ul> : <p>{t('builder.noChanges')}</p>}
        <div className="toolbar"><Button variant="primary" onClick={() => void save()} disabled={busy}>{t('builder.confirmSave')}</Button>
          <Button onClick={() => setReview(false)}>{t('builder.cancel')}</Button></div>
      </section> : null}
    </> : <section className="extension-panel"><PluginWorkshop catalog={catalog} onPluginReady={() => void refreshCatalog()} /></section>}
  </div>;
}
