import { useEffect, useState } from 'react';
import {
  type ExtensionCatalog,
  type ExtensionModule,
  type ExtensionPipeline,
  type PipelinePreview,
  extensionsApi,
} from '../../../api';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { PipelineGraph } from '../PipelineGraph';
import { DeclarativeEditor } from './DeclarativeEditor';
import { ModuleListEditor } from './ModuleListEditor';
import { Field, JsonField, type JsonObject, RESERVED_MODULE_FIELDS, SURVEILLANCE_GROUPS, SchemaFields, isObject, moduleDefaults, moduleOptionLabel, newConfig, parseEditorConfig, pipelineOf, pipelineSources, shortId, updatePipeline } from './shared';

export function TopologyView({ preview }: { preview: PipelinePreview }) {
  const { t } = useI18n();
  const grouped = new Map<string, PipelinePreview['topology']['nodes']>();
  for (const node of preview.topology.nodes) grouped.set(node.stage, [...(grouped.get(node.stage) || []), node]);
  const labelById = new Map(preview.topology.nodes.map((node) => [node.node_id, node.label]));
  return <div className="extension-topology">
    <p>{preview.topology.description}</p>
    {grouped.size ? [...grouped.entries()].map(([stage, nodes]) => <div className="extension-topology-stage" key={stage}>
      <strong>{stage}</strong>
      <div className="extension-topology-nodes">{nodes.map((node) => <span key={node.node_id} title={node.module_id || ''}>{node.label}</span>)}</div>
    </div>) : <p className="hint">{t('builder.emptyTopology')}</p>}
    {preview.topology.edges.length ? <details>
      <summary>{t('builder.connections', { count: preview.topology.edges.length })}</summary>
      <ul>{preview.topology.edges.map((edge, index) => <li key={`${edge.source}-${edge.target}-${index}`}>
        {labelById.get(edge.source) || edge.source} → {labelById.get(edge.target) || edge.target}{edge.label ? ` · ${edge.label}` : ''}
      </li>)}</ul>
    </details> : null}
    {preview.errors.map((error) => <p key={error} className="extension-error">{error}</p>)}
    {preview.warnings.map((warning) => <p key={warning} className="extension-warning">{warning}</p>)}
  </div>;
}

export function PipelineEditor({
  config, setConfig, catalog, pipeline, onPipelineChange,
}: {
  config: JsonObject;
  setConfig: (config: JsonObject) => void;
  catalog: ExtensionCatalog;
  pipeline: ExtensionPipeline;
  onPipelineChange: (pipelineId: string) => void;
}) {
  const { t } = useI18n();
  const [preview, setPreview] = useState<PipelinePreview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [activeStage, setActiveStage] = useState('sources');
  const [declarativeStage, setDeclarativeStage] = useState(0);
  const [graphModuleFocus, setGraphModuleFocus] = useState('');
  const [graphNodeFocus, setGraphNodeFocus] = useState('');
  const [raw, setRaw] = useState(false);
  const [rawText, setRawText] = useState(() => JSON.stringify(config, null, 2));
  const body = pipelineOf(config);
  const sourceChoices = pipelineSources(body);
  const pipelineSchema = pipeline.config_schema;
  useEffect(() => {
    if (!raw) setRawText(JSON.stringify(config, null, 2));
    setPreview(null);
    if (raw) return;
    let current = true;
    const timer = window.setTimeout(() => {
      void extensionsApi.preview(config).then((result) => {
        if (current) { setPreview(result); setPreviewError(''); }
      }).catch((error) => {
        if (current) setPreviewError(error instanceof Error ? error.message : String(error));
      });
    }, 350);
    return () => { current = false; window.clearTimeout(timer); };
  }, [config, raw]);

  const changeBody = (next: JsonObject) => setConfig(updatePipeline(config, () => next));
  const changeGroup = (groupId: string, items: JsonObject[]) => {
    const modules = isObject(body.modules) ? { ...body.modules } : {};
    const extension = isObject(modules[groupId]) ? modules[groupId] : { mode: 'extend', items: [] };
    modules[groupId] = { ...extension, items };
    changeBody({ ...body, modules });
  };
  const selectedPipeline = (identity: string) => {
    const spec = catalog.pipelines.find((candidate) => candidate.config_id === identity || candidate.id === identity);
    if (!spec) return;
    const next = newConfig(spec);
    setConfig(isObject(config.pipeline) ? { ...config, pipeline: { ...pipelineOf(next) } } : next);
    onPipelineChange(spec.config_id);
    setPreview(null);
  };
  const runPreview = async () => {
    try {
      const parsed = raw ? parseEditorConfig(rawText) : config;
      const result = await extensionsApi.preview(parsed);
      setPreview(result);
      setPreviewError('');
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : String(error));
    }
  };

  const selectGraphNode = (node: PipelinePreview['topology']['nodes'][number]) => {
    setGraphModuleFocus(node.module_id || '');
    setGraphNodeFocus(node.node_id);
    if (pipeline.pipeline_id === 'PipelineDeclarative' && node.node_id.startsWith('stage:')) {
      const stageIndex = Number(node.node_id.split(':')[1]);
      if (Number.isInteger(stageIndex)) setDeclarativeStage(stageIndex);
      setActiveStage('declarative');
      return;
    }
    if (node.node_id.startsWith('events:') || node.stage.toLowerCase() === 'events') { setActiveStage('events'); return; }
    const stageMap: Record<string, string> = {
      sources: 'sources', preprocessors: 'preprocessors', detectors: 'detectors', trackers: 'trackers',
      mc_trackers: 'mc_trackers', attributes_roi: 'attributes_roi', attributes_classifier: 'attributes_classifier',
    };
    const sourceStage = node.node_id.split(':')[0];
    if (stageMap[sourceStage]) setActiveStage(stageMap[sourceStage]);
  };

  const surveillanceStageTabs = [
    ...SURVEILLANCE_GROUPS.map((group) => ({ id: group.id, label: t(group.title) })),
    { id: 'events', label: t('builder.eventBranch') },
    { id: 'general', label: t('builder.pipelineSettings') },
  ];

  return <div className="extension-builder-content">
    <div className="extension-form-grid extension-pipeline-picker">
      <Field label={t('builder.pipelineType')}>
        <select value={String(body.pipeline_class || pipeline.config_id)} onChange={(event) => selectedPipeline(event.target.value)}>
          {catalog.pipelines.map((item) => <option key={item.id} value={item.config_id}>{item.display_name} · {item.config_id}</option>)}
        </select>
      </Field>
      {pipeline.description ? <p className="hint extension-description">{pipeline.description}</p> : null}
    </div>

    {!raw && preview ? <section className="extension-subpanel pipeline-topology-panel">
      <div className="extension-section-heading"><h3>{t('builder.pipelineTopology')}</h3><span className="hint">{preview.topology.description}</span></div>
      <PipelineGraph preview={preview} onSelect={selectGraphNode} />
      {preview.errors.length || preview.warnings.length ? <div className="pipeline-topology-messages">
        {preview.errors.map((message) => <p className="extension-error" key={message}>{message}</p>)}
        {preview.warnings.map((message) => <p className="extension-warning" key={message}>{message}</p>)}
      </div> : null}
    </section> : null}

    {!raw && pipeline.pipeline_id === 'PipelineSurveillance' ? <>
      <div className="pipeline-stage-tabs" role="tablist" aria-label={t('builder.pipelineStages')}>
        {surveillanceStageTabs.map((stage) => <button key={stage.id} type="button" role="tab" aria-selected={activeStage === stage.id}
          tabIndex={activeStage === stage.id ? 0 : -1} onClick={() => setActiveStage(stage.id)}
          onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const currentIndex = surveillanceStageTabs.findIndex((item) => item.id === activeStage);
            const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? surveillanceStageTabs.length - 1
              : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + surveillanceStageTabs.length) % surveillanceStageTabs.length;
            const next = surveillanceStageTabs[nextIndex];
            setActiveStage(next.id);
            document.getElementById(`pipeline-stage-tab-${next.id}`)?.focus();
          }} id={`pipeline-stage-tab-${stage.id}`} aria-controls="pipeline-stage-panel">{stage.label}</button>)}
      </div>
      {activeStage !== 'events' && activeStage !== 'general' ? (() => {
        const group = SURVEILLANCE_GROUPS.find((item) => item.id === activeStage);
        if (!group) return null;
        const moduleMap = isObject(body.modules) ? body.modules : {};
        const override = isObject(moduleMap[group.id]) ? moduleMap[group.id] : {};
        const mode = override.mode === 'replace' ? 'replace' : 'extend';
        const items = Array.isArray(override.items) ? override.items.filter(isObject) : [];
        const legacy = Array.isArray(body[group.id]) ? body[group.id].filter(isObject) : [];
        return <section className="extension-subpanel" key={group.id} role="tabpanel" id="pipeline-stage-panel" aria-labelledby={`pipeline-stage-tab-${activeStage}`}>
          <div className="extension-section-heading">
            <h3>{t(group.title)}</h3>
            <Field label={t('builder.extensionMode')}>
              <select value={mode} onChange={(event) => {
                const modules = isObject(body.modules) ? { ...body.modules } : {};
                modules[group.id] = { mode: event.target.value, items };
                changeBody({ ...body, modules });
              }}>
                <option value="extend">{t('builder.extend')}</option>
                <option value="replace">{t('builder.replace')}</option>
              </select>
            </Field>
          </div>
          {mode === 'extend' && legacy.length ? <ModuleListEditor
            modules={catalog.modules}
            items={legacy}
            kind={group.kind}
            stage={group.id}
            title={t('builder.baseModulesEditor', { count: legacy.length })}
            focusModuleId={graphModuleFocus}
            focusNodeId={graphNodeFocus}
            sourceChoices={sourceChoices}
            allowAdd={false}
            onChange={(next) => changeBody({ ...body, [group.id]: next })}
          /> : null}
          {mode === 'replace' && legacy.length ? <p className="hint">{t('builder.replacedModules', { count: legacy.length })}</p> : null}
          <ModuleListEditor
            modules={catalog.modules}
            items={items}
            kind={group.kind}
            stage={group.id}
            title={t(mode === 'extend' ? 'builder.additionalModules' : 'builder.customModules')}
            focusModuleId={graphModuleFocus}
            focusNodeId={graphNodeFocus}
            nodeIndexOffset={mode === 'extend' ? legacy.length : 0}
            sourceChoices={sourceChoices}
            onChange={(next) => changeGroup(group.id, next)}
          />
        </section>;
      })() : null}
      {activeStage === 'events' ? <div role="tabpanel" id="pipeline-stage-panel" aria-labelledby="pipeline-stage-tab-events"><EventRulesEditor config={config} setConfig={setConfig} modules={catalog.modules} defaultEnabled={catalog.default_event_detectors} focusModuleId={graphModuleFocus} /></div> : null}
      {activeStage === 'general' ? <div role="tabpanel" id="pipeline-stage-panel" aria-labelledby="pipeline-stage-tab-general"><SchemaFields schema={pipelineSchema} uiSchema={pipeline.ui_schema} value={body} onChange={changeBody}
        excluded={new Set([...SURVEILLANCE_GROUPS.map((group) => group.id), 'pipeline_class', 'modules'])} />
      </div> : null}
    </> : null}

    {!raw && pipeline.pipeline_id === 'PipelineDeclarative' ? <>
      <DeclarativeEditor body={body} changeBody={changeBody} modules={catalog.modules} activeStage={declarativeStage} onStageChange={setDeclarativeStage}
        focusModuleId={graphModuleFocus} focusNodeId={graphNodeFocus} sourceChoices={sourceChoices} />
      <EventRulesEditor config={config} setConfig={setConfig} modules={catalog.modules} defaultEnabled={catalog.default_event_detectors} focusModuleId={graphModuleFocus} />
    </> : null}
    {!raw && pipeline.pipeline_id === 'PipelineCapture' ? <ModuleListEditor
      modules={catalog.modules}
      items={(Array.isArray(body.sources) ? body.sources : []).filter(isObject)}
      kind="source"
      stage="capture-source"
      title={t('builder.sources')}
      maxItems={1}
      sourceChoices={sourceChoices}
      onChange={(sources) => changeBody({ ...body, sources })}
    /> : null}
    {!raw && !['PipelineSurveillance', 'PipelineDeclarative', 'PipelineCapture'].includes(pipeline.pipeline_id) ? (
      pipelineSchema ? <SchemaFields schema={pipelineSchema} uiSchema={pipeline.ui_schema} value={body} onChange={changeBody} excluded={new Set(['pipeline_class'])} /> : (
        <p className="extension-warning">{t('builder.opaquePipeline')}</p>
      )
    ) : null}

    <details className="extension-json-editor" open={raw} onToggle={(event) => setRaw(event.currentTarget.open)}>
      <summary>{t('builder.rawJson')}</summary>
      <p className="hint">{t('builder.rawJsonHint')}</p>
      <textarea value={rawText} onChange={(event) => {
        const text = event.target.value;
        setRawText(text);
        try {
          const next = parseEditorConfig(text);
          setConfig(next);
          const identity = String(pipelineOf(next).pipeline_class || '');
          const selected = catalog.pipelines.find((item) => item.config_id === identity || item.id === identity);
          if (selected) onPipelineChange(selected.config_id);
        } catch { /* keep invalid text for correction */ }
      }} spellCheck={false} />
    </details>

    <div className="toolbar">
      <Button variant="outline" onClick={() => void runPreview()}>{t('builder.preview')}</Button>
      {preview?.valid ? <span className="extension-valid">{t('builder.valid')}</span> : null}
      {preview && !preview.valid ? <span className="extension-error">{t('builder.invalid')}</span> : null}
      {previewError ? <span className="extension-error">{previewError}</span> : null}
    </div>
  </div>;
}

function EventRulesEditor({ config, setConfig, modules, defaultEnabled, focusModuleId }: {
  config: JsonObject;
  setConfig: (value: JsonObject) => void;
  modules: ExtensionModule[];
  defaultEnabled: string[];
  focusModuleId?: string;
}) {
  const { t } = useI18n();
  const rules = isObject(config.events_detectors) ? config.events_detectors : {};
  const enabled = Array.isArray(rules.enabled) ? rules.enabled.map(String) : defaultEnabled;
  const configured = Object.entries(rules).filter(([key, value]) => key !== 'enabled' && isObject(value));
  const itemMap = new Map(configured);
  const items = [...new Set([...defaultEnabled, ...configured.map(([key]) => key)])].map((id) => [id, itemMap.get(id) || {}] as [string, JsonObject]);
  const candidates = modules.filter((module) => module.kind === 'event_detector' || module.kind === 'alarm_detector');
  const update = (next: JsonObject) => setConfig({ ...config, events_detectors: next });
  const add = (id: string) => {
    const module = candidates.find((candidate) => candidate.id === id);
    if (!module || Object.prototype.hasOwnProperty.call(rules, id)) return;
    update({ ...rules, enabled: [...enabled, id], [id]: moduleDefaults(module) });
  };
  const [selected, setSelected] = useState('');
  const [activeId, setActiveId] = useState('');
  useEffect(() => {
    if (!focusModuleId) return;
    if (items.some(([id, item]) => id === focusModuleId || item.module_id === focusModuleId)) setActiveId(focusModuleId);
  }, [focusModuleId, rules]);
  const active = items.find(([id, item]) => id === activeId || item.module_id === activeId) || items[0];
  return <section className="extension-subpanel">
    <div className="extension-section-heading"><h3>{t('builder.eventBranch')}</h3><span className="hint">{t('builder.eventBranchHint')}</span></div>
    <div className="module-inspector-layout">
      <div className="module-list" role="list" aria-label={t('builder.eventBranch')}>
        {items.map(([id, item]) => {
          const spec = candidates.find((module) => module.id === id || module.module_id === id || module.id === item.module_id);
          const isActive = active?.[0] === id;
          return <div className={`module-list-item-wrap${isActive ? ' is-active' : ''}`} key={id}>
            <button type="button" className={`module-list-item${isActive ? ' is-active' : ''}`} aria-pressed={isActive} onClick={() => setActiveId(id)}>
              <span className="module-list-name">{spec?.display_name || shortId(id)}</span><small>{id}</small>
              <span className={`module-enabled-dot${enabled.includes(id) ? '' : ' is-disabled'}`} />
            </button>
            <label className="module-list-enabled"><input type="checkbox" checked={enabled.includes(id)} onChange={(event) => update({
            ...rules,
            enabled: event.target.checked ? [...enabled, id] : enabled.filter((name) => name !== id),
          })} /> {t('builder.enabled')}</label>
          </div>;
        })}
        <div className="module-add-control">
          <select value={selected} onChange={(event) => setSelected(event.target.value)} aria-label={t('builder.chooseModule')}><option value="">{t('builder.chooseModule')}</option>
            {candidates.map((module) => <option key={module.id} value={module.id}>{moduleOptionLabel(module, t)}</option>)}
          </select>
          <Button variant="primary" onClick={() => { add(selected); setActiveId(selected); setSelected(''); }} disabled={!selected}>{t('builder.addRule')}</Button>
        </div>
        {!candidates.length ? <span className="hint">{t('builder.noEventModules')}</span> : null}
      </div>
      {active ? (() => {
        const [id, item] = active;
        const spec = candidates.find((module) => module.id === id || module.module_id === id || module.id === item.module_id);
        return <article className="module-inspector">
          <div className="extension-module-heading"><div><strong>{spec?.display_name || shortId(id)}</strong><small>{id}</small></div>
            {!defaultEnabled.includes(id) ? <Button size="sm" variant="danger" onClick={() => {
              const next = { ...rules };
              delete next[id];
              update({ ...next, enabled: enabled.filter((name) => name !== id) });
              setActiveId('');
            }}>{t('builder.remove')}</Button> : null}
          </div>
          {spec?.config_schema ? <SchemaFields schema={spec.config_schema} uiSchema={spec.ui_schema} value={item} onChange={(next) => update({ ...rules, [id]: { ...item, ...next } })} excluded={RESERVED_MODULE_FIELDS} /> : (
            <details><summary>{t('builder.rawModule')}</summary><JsonField value={item} onChange={(next) => { if (isObject(next)) update({ ...rules, [id]: next }); }} /></details>
          )}
        </article>;
      })() : <div className="module-inspector"><p className="hint">{t('builder.noEventModules')}</p></div>}
    </div>
  </section>;
}
