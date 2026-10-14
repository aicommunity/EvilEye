import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  configsList,
  configGet,
  extensionsApi,
  type ExtensionCatalog,
  type ExtensionModule,
  type ExtensionPipeline,
  type PipelinePreview,
  type PluginOperation,
} from '../../api';
import { Button } from '../../components/ui';
import { PageHeader } from '../../components/ui/PageHeader';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { schemaDefaults } from './schemaDefaults';
import { SchemaForm } from './SchemaForm';
import { PipelineGraph } from './PipelineGraph';

type JsonObject = Record<string, any>;
type BuilderTab = 'pipeline' | 'plugins';
type Schema = Record<string, any>;

function isRecentOperationFailure(operation: PluginOperation): boolean {
  return operation.status === 'failed'
    && typeof operation.updated_at === 'number'
    && Date.now() / 1000 - operation.updated_at < 30;
}

function operationStatusLabel(operation: PluginOperation): string {
  return isRecentOperationFailure(operation) ? 'builder.status.settling' : `builder.status.${operation.status}`;
}

const SURVEILLANCE_GROUPS: Array<{ id: string; kind: string; title: string }> = [
  { id: 'sources', kind: 'source', title: 'builder.sources' },
  { id: 'preprocessors', kind: 'processor_item', title: 'builder.preprocessors' },
  { id: 'detectors', kind: 'processor_item', title: 'builder.detectors' },
  { id: 'trackers', kind: 'processor_item', title: 'builder.trackers' },
  { id: 'mc_trackers', kind: 'batch_processor', title: 'builder.multiTrackers' },
  { id: 'attributes_roi', kind: 'processor_item', title: 'builder.roiAttributes' },
  { id: 'attributes_classifier', kind: 'processor_item', title: 'builder.classifiers' },
];

const RESERVED_MODULE_FIELDS = new Set([
  'type', 'module_id', 'enable', 'enabled', 'execution_mode', 'source_ids', 'queue_size',
  'worker_count', 'ipc_mode', 'mp_restart_on_exit', 'mp_no_restart_exit_codes',
]);
const LEGACY_DECLARATIVE_STAGES: Array<[string, string]> = [
  ['sources', 'source'],
  ['preprocessors', 'frame'],
  ['detectors', 'step'],
  ['trackers', 'step'],
  ['mc_trackers', 'step'],
  ['attributes_roi', 'step'],
  ['attributes_classifier', 'step'],
];

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function pipelineOf(config: JsonObject): JsonObject {
  return isObject(config.pipeline) ? config.pipeline : config;
}

function updatePipeline(config: JsonObject, update: (pipeline: JsonObject) => JsonObject): JsonObject {
  if (isObject(config.pipeline)) return { ...config, pipeline: update(config.pipeline) };
  return update(config);
}

function newConfig(pipeline: ExtensionPipeline): JsonObject {
  const body = schemaDefaults(pipeline.config_schema);
  body.pipeline_class = pipeline.config_id;
  if (pipeline.pipeline_id === 'PipelineSurveillance') {
    for (const group of SURVEILLANCE_GROUPS) body[group.id] = [];
    body.modules = {};
  } else if (pipeline.pipeline_id === 'PipelineDeclarative') {
    body.stages = [];
  } else if (pipeline.pipeline_id === 'PipelineCapture') {
    body.sources = [];
  }
  return { pipeline: body };
}

function moduleCandidates(modules: ExtensionModule[], kind: string, stage: string): ExtensionModule[] {
  return modules.filter((module) => {
    if (module.kind !== kind) return false;
    if (stage === 'capture-source') return module.id === 'evileye/VideoCaptureOpencv';
    if (stage === 'step') return true;
    if (stage === 'frame') return !module.stages.length || module.stages.some((item) => ['frame', 'preprocessors', 'preprocessor'].includes(item));
    return !module.stages.length || module.stages.includes(stage);
  }).sort((left, right) => {
    const pluginOrder = Number(left.plugin_id === 'evileye') - Number(right.plugin_id === 'evileye');
    return pluginOrder || left.display_name.localeCompare(right.display_name) || left.id.localeCompare(right.id);
  });
}

function moduleOptionLabel(module: ExtensionModule, translate: (key: string) => string): string {
  const marker = module.plugin_id === 'evileye' ? '' : `${translate('builder.pluginMarker')} · `;
  return `${marker}${module.display_name} · ${module.id}`;
}

function moduleDefaults(module: ExtensionModule, sourceId = 0): JsonObject {
  const value = schemaDefaults(module.config_schema);
  for (const key of RESERVED_MODULE_FIELDS) delete value[key];
  const item: JsonObject = { module_id: module.id, enable: true, ...value };
  if (module.execution_modes.length) {
    item.execution_mode = module.default_execution_mode || module.execution_modes[0];
  }
  if (module.kind === 'source') {
    item.source_ids = [sourceId];
    const schemaProperties = isObject(module.config_schema?.properties) ? module.config_schema?.properties : {};
    if (Object.prototype.hasOwnProperty.call(schemaProperties, 'source_id')) item.source_id = sourceId;
  }
  return item;
}

type SourceChoice = { id: number; label: string };

function pipelineSources(body: JsonObject): SourceChoice[] {
  const moduleSources = isObject(body.modules) && isObject(body.modules.sources) ? body.modules.sources : {};
  const extensionItems = Array.isArray(moduleSources.items) ? moduleSources.items.filter(isObject) : [];
  const legacyItems = Array.isArray(body.sources) ? body.sources.filter(isObject) : [];
  const declarativeItems = Array.isArray(body.stages)
    ? body.stages.filter(isObject).filter((stage) => stage.kind === 'source').flatMap((stage) => Array.isArray(stage.items) ? stage.items.filter(isObject) : [])
    : [];
  const sourceItems = moduleSources.mode === 'replace' ? [...extensionItems, ...declarativeItems] : [...legacyItems, ...extensionItems, ...declarativeItems];
  const choices = new Map<number, string>();
  sourceItems.forEach((item, index) => {
    const ids = Array.isArray(item.source_ids) ? item.source_ids : [item.source_id ?? index];
    const names = Array.isArray(item.source_names) ? item.source_names : [];
    ids.forEach((rawId, nameIndex) => {
      const id = Number(rawId);
      if (!Number.isInteger(id) || choices.has(id)) return;
      const explicit = names[nameIndex] ?? item.source_name ?? item.camera_name ?? item.name ?? item.display_name;
      choices.set(id, String(explicit || `Source ${id + 1}`));
    });
  });
  return [...choices.entries()].sort(([left], [right]) => left - right).map(([id, label]) => ({ id, label }));
}

function SourceIdsField({ value, choices, onChange, label }: {
  value: unknown;
  choices: SourceChoice[];
  onChange: (value: number[]) => void;
  label: string;
}) {
  const { t } = useI18n();
  const selected = Array.isArray(value) ? value.map(Number).filter(Number.isInteger) : [];
  if (!choices.length) return <Field label={label} hint={t('builder.jsonArrayHint')}>
    <JsonField value={Array.isArray(value) ? value : []} onChange={(next) => { if (Array.isArray(next) && next.every((item) => Number.isInteger(Number(item)))) onChange(next.map(Number)); }} rows={2} />
  </Field>;
  const allChoices = [...choices];
  for (const id of selected) if (!allChoices.some((item) => item.id === id)) allChoices.push({ id, label: t('builder.unknownSource', { id }) });
  return <fieldset className="source-id-picker">
    <legend>{label}</legend>
    {allChoices.map((source) => <label key={source.id}>
      <input type="checkbox" checked={selected.includes(source.id)} onChange={(event) => {
        const next = new Set(selected);
        if (event.target.checked) next.add(source.id);
        else next.delete(source.id);
        onChange([...next].sort((left, right) => left - right));
      }} />
      <span>{source.label}</span><code>{source.id}</code>
    </label>)}
  </fieldset>;
}

function declarativeStages(body: JsonObject): JsonObject[] {
  if (Array.isArray(body.stages) && body.stages.length) return body.stages.filter(isObject);
  return LEGACY_DECLARATIVE_STAGES.flatMap(([name, kind]) => {
    const items = body[name];
    return Array.isArray(items) && items.length ? [{ name, kind, items: items.filter(isObject) }] : [];
  });
}

function shortId(moduleId: unknown): string {
  const value = String(moduleId || 'module');
  const parts = value.split('/');
  return parts[parts.length - 1] || value;
}

function redacted(value: unknown, key = ''): unknown {
  if (/password|secret|token|credential|username|api_key|private_key/i.test(key)) return '••••••';
  if (Array.isArray(value)) return value.map((item) => redacted(item));
  if (isObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([child, item]) => [child, redacted(item, child)]));
  }
  if (typeof value === 'string') return value.replace(/:\/\/[^/@]+:[^/@]+@/g, '://••••••@');
  return value;
}

function jsonDiff(before: unknown, after: unknown, path = '$'): string[] {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (isObject(before) && isObject(after)) {
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...keys].flatMap((key) => {
      if (!(key in before)) return [`+ ${path}.${key}: ${JSON.stringify(redacted(after[key], key))}`];
      if (!(key in after)) return [`− ${path}.${key}: ${JSON.stringify(redacted(before[key], key))}`];
      return jsonDiff(before[key], after[key], `${path}.${key}`);
    });
  }
  if (Array.isArray(before) && Array.isArray(after)) {
    const length = Math.max(before.length, after.length);
    return Array.from({ length }, (_, index) => {
      if (index >= before.length) return `+ ${path}[${index}]: ${JSON.stringify(redacted(after[index]))}`;
      if (index >= after.length) return `− ${path}[${index}]: ${JSON.stringify(redacted(before[index]))}`;
      return jsonDiff(before[index], after[index], `${path}[${index}]`);
    }).flat();
  }
  return [`~ ${path}: ${JSON.stringify(redacted(before, path))} → ${JSON.stringify(redacted(after, path))}`];
}

function parseEditorConfig(raw: string): JsonObject {
  const parsed: unknown = JSON.parse(raw);
  if (!isObject(parsed)) throw new Error('JSON root must be an object');
  return parsed;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="extension-field"><span>{label}</span>{children}{hint ? <small>{hint}</small> : null}</label>;
}

function JsonField({ value, onChange, rows = 3 }: { value: unknown; onChange: (value: unknown) => void; rows?: number }) {
  const [draft, setDraft] = useState(JSON.stringify(value ?? null, null, 2));
  const [invalid, setInvalid] = useState(false);
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    if (!editing) setDraft(JSON.stringify(value ?? null, null, 2));
  }, [value, editing]);
  return <>
    <textarea rows={rows} value={draft} aria-invalid={invalid} onBlur={() => setEditing(false)} onChange={(event) => {
      setEditing(true);
      const text = event.target.value;
      setDraft(text);
      try {
        onChange(JSON.parse(text));
        setInvalid(false);
      } catch {
        setInvalid(true);
      }
    }} />
    {invalid ? <small className="extension-error">Enter valid JSON to apply this value.</small> : null}
  </>;
}

function SchemaFields({
  schema,
  value,
  onChange,
  uiSchema,
  excluded = new Set<string>(),
}: {
  schema?: Schema | null;
  value: JsonObject;
  onChange: (next: JsonObject) => void;
  excluded?: Set<string>;
  uiSchema?: Record<string, unknown> | null;
}) {
  const { t } = useI18n();
  return <SchemaForm schema={schema} value={value} onChange={onChange} excluded={excluded} uiSchema={uiSchema} emptyMessage={t('builder.noSchemaFields')} />;
}

export function ModuleListEditor({
  modules,
  items,
  kind,
  stage,
  title,
  onChange,
  maxItems,
  focusModuleId,
  allowAdd = true,
  sourceChoices = [],
}: {
  modules: ExtensionModule[];
  items: JsonObject[];
  kind: string;
  stage: string;
  title: string;
  onChange: (items: JsonObject[]) => void;
  maxItems?: number;
  focusModuleId?: string;
  allowAdd?: boolean;
  sourceChoices?: SourceChoice[];
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const candidates = moduleCandidates(modules, kind, stage);
  useEffect(() => {
    if (!focusModuleId) return;
    const index = items.findIndex((item) => String(item.module_id || item.type || '') === focusModuleId);
    if (index >= 0) setActiveIndex(index);
  }, [focusModuleId, items]);
  const add = () => {
    const module = candidates.find((item) => item.id === selected);
    if (!module || (maxItems !== undefined && items.length >= maxItems)) return;
    const usedSourceIds = new Set(sourceChoices.map((item) => item.id));
    let sourceId = 0;
    while (usedSourceIds.has(sourceId)) sourceId += 1;
    onChange([...items, moduleDefaults(module, sourceId)]);
    setActiveIndex(items.length);
    setSelected('');
  };
  const move = (index: number, shift: number) => {
    const target = index + shift;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
    if (activeIndex === index) setActiveIndex(target);
    else if (activeIndex === target) setActiveIndex(index);
  };
  const active = items[activeIndex] ? activeIndex : Math.max(0, items.length - 1);
  const activeItem = items[active];
  const moduleId = activeItem?.module_id || activeItem?.type || candidates[0]?.id || '';
  const activeSpec = modules.find((module) => module.id === moduleId || module.module_id === moduleId);
  const executionModes = activeSpec?.execution_modes || [];
  const configIsNested = isObject(activeItem?.config);
  const formValue = configIsNested ? activeItem.config : activeItem;
  const updateActive = (update: (item: JsonObject) => JsonObject) => onChange(items.map((item, itemIndex) => itemIndex === active ? update(item) : item));
  const updateForm = (next: JsonObject) => {
    const clean = { ...next };
    for (const key of RESERVED_MODULE_FIELDS) delete clean[key];
    updateActive((entry) => configIsNested ? { ...entry, config: clean } : { ...entry, ...clean });
  };
  return <section className="extension-subpanel">
    <div className="extension-section-heading"><h3>{title} <span className="extension-count">{items.length}</span></h3></div>
    <div className="module-inspector-layout">
      <div className="module-list" role="group" aria-label={title}>
        {items.map((item, index) => {
      const moduleId = item.module_id || item.type || candidates[0]?.id || '';
      const spec = modules.find((module) => module.id === moduleId || module.module_id === moduleId);
          return <button key={`${String(moduleId)}-${index}`} type="button" aria-pressed={active === index}
            className={`module-list-item${active === index ? ' is-active' : ''}`} onClick={() => setActiveIndex(index)}>
            <span className="module-list-name">{spec?.display_name || shortId(moduleId)}</span>
            <small>{String(moduleId)}</small>
            <span className={`module-enabled-dot${item.enable === false || item.enabled === false ? ' is-disabled' : ''}`} aria-label={item.enable === false || item.enabled === false ? t('builder.disabled') : t('builder.enabled')} />
          </button>;
        })}
        {!items.length ? <p className="hint">{t('builder.noModules')}</p> : null}
        {allowAdd ? <div className="module-add-control">
          <select aria-label={t('builder.chooseModule')} value={selected} onChange={(event) => setSelected(event.target.value)}>
            <option value="">{t('builder.chooseModule')}</option>
            {candidates.map((module) => <option key={module.id} value={module.id}>{moduleOptionLabel(module, t)}</option>)}
          </select>
          <Button variant="primary" onClick={add} disabled={!selected || (maxItems !== undefined && items.length >= maxItems)}>{t('builder.addModule')}</Button>
        </div> : null}
        {allowAdd && !candidates.length ? <span className="hint">{t('builder.noModules')}</span> : null}
      </div>
      {activeItem ? <article className="module-inspector">
        <div className="extension-module-heading">
          <div><strong>{activeSpec?.display_name || shortId(moduleId)}</strong><small>{String(moduleId)}</small></div>
          <div className="toolbar">
            <Button size="sm" onClick={() => move(active, -1)} disabled={active === 0} aria-label={t('builder.moveUp')}>↑</Button>
            <Button size="sm" onClick={() => move(active, 1)} disabled={active === items.length - 1} aria-label={t('builder.moveDown')}>↓</Button>
            <Button size="sm" variant="danger" onClick={() => { onChange(items.filter((_, index) => index !== active)); setActiveIndex(Math.max(0, active - 1)); }}>{t('builder.remove')}</Button>
          </div>
        </div>
        {!activeSpec ? <p className="extension-warning">{t('builder.unknownModule')}</p> : null}
        <div className="extension-module-controls">
          <label><input type="checkbox" checked={activeItem.enable !== false && activeItem.enabled !== false} onChange={(event) => updateActive((entry) => ({ ...entry, enable: event.target.checked }))} /> {t('builder.enabled')}</label>
          {executionModes.length > 0 ? <Field label={t('builder.executionMode')}>
            <select value={String(activeItem.execution_mode || activeSpec?.default_execution_mode || executionModes[0])}
              onChange={(event) => updateActive((entry) => ({ ...entry, execution_mode: event.target.value }))}>
              {executionModes.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
            </select>
          </Field> : null}
          {(Array.isArray(activeItem.source_ids) || sourceChoices.length > 0) ? <SourceIdsField
            label={t('builder.sourceIds')} value={activeItem.source_ids} choices={sourceChoices}
            onChange={(value) => updateActive((entry) => ({ ...entry, source_ids: value }))} /> : null}
        </div>
        {activeSpec?.config_schema ? <SchemaFields key={`${active}-${moduleId}`} schema={activeSpec.config_schema} uiSchema={activeSpec.ui_schema} value={formValue || {}} onChange={updateForm} excluded={RESERVED_MODULE_FIELDS} /> : (
          <details><summary>{t('builder.rawModule')}</summary><JsonField value={activeItem} onChange={(value) => { if (isObject(value)) updateActive(() => value); }} /></details>
        )}
      </article> : null}
    </div>
  </section>;
}

function TopologyView({ preview }: { preview: PipelinePreview }) {
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

function PipelineEditor({
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
      <DeclarativeEditor body={body} changeBody={changeBody} modules={catalog.modules} activeStage={declarativeStage} onStageChange={setDeclarativeStage} focusModuleId={graphModuleFocus} sourceChoices={sourceChoices} />
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

export function DeclarativeEditor({ body, changeBody, modules, activeStage, onStageChange, focusModuleId, sourceChoices }: {
  body: JsonObject;
  changeBody: (body: JsonObject) => void;
  modules: ExtensionModule[];
  activeStage: number;
  onStageChange: (index: number) => void;
  focusModuleId?: string;
  sourceChoices: SourceChoice[];
}) {
  const { t } = useI18n();
  const stages = declarativeStages(body);
  const updateStages = (next: JsonObject[]) => changeBody({ ...body, stages: next });
  useEffect(() => {
    if (stages.length && activeStage >= stages.length) onStageChange(stages.length - 1);
  }, [activeStage, onStageChange, stages.length]);
  const move = (index: number, shift: number) => {
    const target = index + shift;
    if (target < 0 || target >= stages.length) return;
    const next = [...stages];
    [next[index], next[target]] = [next[target], next[index]];
    updateStages(next);
    const activeIndex = next.indexOf(stages[activeStage]);
    if (activeIndex >= 0) onStageChange(activeIndex);
  };
  const removeStage = (index: number) => {
    const selected = stages[activeStage];
    const next = stages.filter((_, stageIndex) => stageIndex !== index);
    const nextActive = selected && selected !== stages[index] ? next.indexOf(selected) : Math.min(index, next.length - 1);
    updateStages(next);
    onStageChange(Math.max(0, nextActive));
  };
  return <section className="extension-subpanel">
    <div className="extension-section-heading"><h3>{t('builder.linearStages')}</h3>
      <Button variant="primary" onClick={() => updateStages([...stages, { name: `stage_${stages.length + 1}`, kind: 'step', items: [] }])}>{t('builder.addStage')}</Button>
    </div>
    <div className="pipeline-stage-tabs declarative-stage-tabs" role="tablist" aria-label={t('builder.pipelineStages')}>
      {stages.map((stage, index) => <button key={`${String(stage.name)}-${index}`} type="button" role="tab" aria-selected={activeStage === index}
        tabIndex={activeStage === index ? 0 : -1} onClick={() => onStageChange(index)}
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const target = event.key === 'Home' ? 0 : event.key === 'End' ? stages.length - 1
            : (index + (event.key === 'ArrowRight' ? 1 : -1) + stages.length) % stages.length;
          onStageChange(target);
          document.getElementById(`declarative-stage-tab-${target}`)?.focus();
        }} id={`declarative-stage-tab-${index}`} aria-controls="declarative-stage-panel">{String(stage.name || `Stage ${index + 1}`)}</button>)}
    </div>
    {stages[activeStage] ? (() => {
      const index = activeStage;
      const stage = stages[index];
      const kind = ['source', 'frame', 'step'].includes(String(stage.kind)) ? String(stage.kind) : 'step';
      const moduleKind = kind === 'source' ? 'source' : 'processor_item';
      return <article className="extension-stage-card" key={`${String(stage.name)}-${index}`} role="tabpanel" id="declarative-stage-panel" aria-labelledby={`declarative-stage-tab-${index}`}>
        <div className="extension-stage-heading">
          <Field label={t('builder.stageName')}><input value={String(stage.name || '')} onChange={(event) => updateStages(stages.map((item, i) => i === index ? { ...item, name: event.target.value } : item))} /></Field>
          <Field label={t('builder.stageKind')}><select value={kind} onChange={(event) => updateStages(stages.map((item, i) => i === index ? { ...item, kind: event.target.value } : item))}>
            <option value="source">{t('builder.sourceStage')}</option><option value="frame">{t('builder.frameStage')}</option><option value="step">{t('builder.stepStage')}</option>
          </select></Field>
          <div className="toolbar">
            <Button size="sm" onClick={() => move(index, -1)} disabled={index === 0} aria-label={t('builder.moveUp')}>↑</Button>
            <Button size="sm" onClick={() => move(index, 1)} disabled={index === stages.length - 1} aria-label={t('builder.moveDown')}>↓</Button>
          <Button size="sm" variant="danger" onClick={() => removeStage(index)}>{t('builder.removeStage')}</Button>
          </div>
        </div>
        <ModuleListEditor modules={modules} items={(Array.isArray(stage.items) ? stage.items : []).filter(isObject)} kind={moduleKind} stage={kind}
          title={t('builder.stageModules')} focusModuleId={focusModuleId} sourceChoices={sourceChoices} onChange={(items) => updateStages(stages.map((item, i) => i === index ? { ...item, items } : item))} />
      </article>;
    })() : <p className="hint">{t('builder.noStages')}</p>}
    {pipelineSchemaFields(body) ? <p className="hint">{t('builder.finalResultsField')} <input value={String(body.final_results || '')} placeholder={t('builder.finalResultsPlaceholder')}
      onChange={(event) => changeBody({ ...body, final_results: event.target.value || undefined })} /></p> : null}
  </section>;
}

function pipelineSchemaFields(body: JsonObject): boolean {
  return Object.prototype.hasOwnProperty.call(body, 'final_results') || body.pipeline_class === 'PipelineDeclarative';
}

function OpaqueConfigEditor({
  config,
  pipelineId,
  catalog,
  onConfig,
  onPipeline,
}: {
  config: JsonObject;
  pipelineId: string;
  catalog: ExtensionCatalog;
  onConfig: (config: JsonObject) => void;
  onPipeline: (pipelineId: string) => void;
}) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(JSON.stringify(config, null, 2));
  return <div className="extension-builder-content">
    <Field label={t('builder.pipelineType')}>
      <select value={pipelineId} onChange={(event) => {
        const spec = catalog.pipelines.find((item) => item.config_id === event.target.value);
        if (!spec) return;
        onPipeline(spec.config_id);
        onConfig(updatePipeline(config, (body) => ({ ...body, pipeline_class: spec.config_id })));
      }}>
        <option value={pipelineId}>{pipelineId} · {t('builder.unknownPipeline')}</option>
        {catalog.pipelines.map((item) => <option key={item.id} value={item.config_id}>{item.display_name} · {item.config_id}</option>)}
      </select>
    </Field>
    <p className="extension-warning">{t('builder.manualPipelineHint')}</p>
    <Field label={t('builder.rawJson')}>
      <textarea className="extension-raw-editor" rows={22} value={raw} spellCheck={false} onChange={(event) => {
        const text = event.target.value;
        setRaw(text);
        try { onConfig(parseEditorConfig(text)); } catch { /* keep invalid JSON for correction */ }
      }} />
    </Field>
  </div>;
}

function PluginWorkshop({ catalog, onPluginReady }: { catalog: ExtensionCatalog; onPluginReady: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
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
      const created = await extensionsApi.createPlugin(name, template);
      setOperation(created);
      setRecentOperations((items) => [created, ...items.filter((item) => item.id !== created.id)].slice(0, 20));
      setPollingFailed(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  return <div className="extension-builder-content">
    <p className="hint">{t('builder.pluginHint')}</p>
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
        <Field label={t('builder.template')}>
          <select value={template} onChange={(event) => setTemplate(event.target.value)}>
            {catalog.templates.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.module_id}</option>)}
          </select>
        </Field>
      </div>
      {catalog.templates.find((item) => item.id === template)?.description ? <p className="hint">{catalog.templates.find((item) => item.id === template)?.description}</p> : null}
      <Button variant="primary" onClick={() => void create()} disabled={busy || !name.trim()}>{busy ? t('builder.creating') : t('builder.createInstall')}</Button>
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
