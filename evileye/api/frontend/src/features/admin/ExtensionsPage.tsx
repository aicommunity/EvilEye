import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';

type JsonObject = Record<string, any>;
type BuilderTab = 'pipeline' | 'plugins';
type Schema = Record<string, any>;

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

function schemaDefaults(schema?: Schema | null): JsonObject {
  const result: JsonObject = {};
  const properties = isObject(schema?.properties) ? schema.properties : {};
  for (const [key, field] of Object.entries(properties)) {
    if (!isObject(field)) continue;
    if (Object.prototype.hasOwnProperty.call(field, 'default')) result[key] = field.default;
    else if (field.type === 'object' && isObject(field.properties)) result[key] = schemaDefaults(field);
    else if (field.type === 'array') result[key] = [];
  }
  return result;
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
  });
}

function moduleDefaults(module: ExtensionModule): JsonObject {
  const value = schemaDefaults(module.config_schema);
  for (const key of RESERVED_MODULE_FIELDS) delete value[key];
  const item: JsonObject = { module_id: module.id, enable: true, ...value };
  if (module.execution_modes.length) {
    item.execution_mode = module.default_execution_mode || module.execution_modes[0];
  }
  if (module.kind === 'source') item.source_ids = [0];
  return item;
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
  excluded = new Set<string>(),
}: {
  schema?: Schema | null;
  value: JsonObject;
  onChange: (next: JsonObject) => void;
  excluded?: Set<string>;
}) {
  const { t } = useI18n();
  const properties = isObject(schema?.properties) ? schema.properties as Record<string, Schema> : {};
  const fields = Object.entries(properties).filter(([key]) => !excluded.has(key));
  if (!schema || !fields.length) return <p className="hint">{t('builder.noSchemaFields')}</p>;

  function setValue(key: string, next: unknown) {
    const result = { ...value };
    if (next === undefined) delete result[key];
    else result[key] = next;
    onChange(result);
  }

  return <div className="extension-form-grid">
    {fields.map(([key, field]) => {
      const current = Object.prototype.hasOwnProperty.call(value, key) ? value[key] : field.default;
      const fieldType = Array.isArray(field.type) ? field.type.find((item: string) => item !== 'null') : field.type;
      const secret = Boolean(field.secret || field.writeOnly || /password|secret|token|api_key|private_key/i.test(key));
      const hint = field.description || (secret ? t('builder.secretHint') : undefined);
      let input: ReactNode;
      if (Array.isArray(field.enum)) {
        input = <select value={String(current ?? '')} onChange={(event) => {
          const option = field.enum.find((entry: unknown) => String(entry) === event.target.value);
          setValue(key, option);
        }}>
          {!field.enum.some((entry: unknown) => String(entry) === String(current ?? '')) ? <option value="">—</option> : null}
          {field.enum.map((option: unknown) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}
        </select>;
      } else if (fieldType === 'boolean') {
        input = <input type="checkbox" checked={Boolean(current)} onChange={(event) => setValue(key, event.target.checked)} />;
      } else if (fieldType === 'object' || fieldType === 'array' || fieldType === undefined) {
        input = <JsonField value={current ?? (fieldType === 'array' ? [] : {})} onChange={(next) => setValue(key, next)} />;
      } else {
        const isNumber = fieldType === 'number' || fieldType === 'integer';
        input = <input
          type={secret ? 'password' : isNumber ? 'number' : 'text'}
          step={fieldType === 'integer' ? 1 : 'any'}
          min={field.minimum}
          max={field.maximum}
          placeholder={secret && current ? t('builder.secretConfigured') : ''}
          value={secret ? '' : current ?? ''}
          onChange={(event) => {
            if (!event.target.value && secret) return;
            if (isNumber) {
              if (event.target.value === '') return setValue(key, undefined);
              const numberValue = Number(event.target.value);
              if (Number.isFinite(numberValue)) setValue(key, numberValue);
            } else setValue(key, event.target.value);
          }}
        />;
      }
      return <Field key={key} label={field.title || key} hint={hint}>{input}</Field>;
    })}
  </div>;
}

function ModuleListEditor({
  modules,
  items,
  kind,
  stage,
  title,
  onChange,
  maxItems,
}: {
  modules: ExtensionModule[];
  items: JsonObject[];
  kind: string;
  stage: string;
  title: string;
  onChange: (items: JsonObject[]) => void;
  maxItems?: number;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState('');
  const candidates = moduleCandidates(modules, kind, stage);
  const add = () => {
    const module = candidates.find((item) => item.id === selected);
    if (!module || (maxItems !== undefined && items.length >= maxItems)) return;
    onChange([...items, moduleDefaults(module)]);
    setSelected('');
  };
  const move = (index: number, shift: number) => {
    const target = index + shift;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  return <section className="extension-subpanel">
    <h3>{title} <span className="extension-count">{items.length}</span></h3>
    {items.map((item, index) => {
      const moduleId = item.module_id || item.type || candidates[0]?.id || '';
      const spec = modules.find((module) => module.id === moduleId || module.module_id === moduleId);
      const schema = spec?.config_schema;
      const executionModes = spec?.execution_modes || [];
      const configIsNested = isObject(item.config);
      const formValue = configIsNested ? item.config : item;
      const updateForm = (next: JsonObject) => {
        const clean = { ...next };
        for (const key of RESERVED_MODULE_FIELDS) delete clean[key];
        onChange(items.map((entry, itemIndex) => itemIndex === index
          ? (configIsNested ? { ...entry, config: clean } : { ...entry, ...clean })
          : entry));
      };
      return <article key={`${String(moduleId)}-${index}`} className="extension-module-card">
        <div className="extension-module-heading">
          <strong>{spec?.display_name || shortId(moduleId)} <small>{String(moduleId)}</small></strong>
          <div className="toolbar">
            <Button size="sm" onClick={() => move(index, -1)} disabled={index === 0} aria-label={t('builder.moveUp')}>↑</Button>
            <Button size="sm" onClick={() => move(index, 1)} disabled={index === items.length - 1} aria-label={t('builder.moveDown')}>↓</Button>
            <Button size="sm" variant="danger" onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}>{t('builder.remove')}</Button>
          </div>
        </div>
        {!spec ? <p className="extension-warning">{t('builder.unknownModule')}</p> : null}
        <div className="extension-module-controls">
          <label><input type="checkbox" checked={item.enable !== false && item.enabled !== false} onChange={(event) => {
            onChange(items.map((entry, itemIndex) => itemIndex === index ? { ...entry, enable: event.target.checked } : entry));
          }} /> {t('builder.enabled')}</label>
          {executionModes.length > 0 ? <Field label={t('builder.executionMode')}>
            <select value={String(item.execution_mode || spec?.default_execution_mode || executionModes[0])}
              onChange={(event) => onChange(items.map((entry, itemIndex) => itemIndex === index ? { ...entry, execution_mode: event.target.value } : entry))}>
              {executionModes.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
            </select>
          </Field> : null}
          {Array.isArray(item.source_ids) ? <Field label={t('builder.sourceIds')} hint={t('builder.jsonArrayHint')}>
            <JsonField value={item.source_ids} onChange={(value) => onChange(items.map((entry, itemIndex) => itemIndex === index ? { ...entry, source_ids: value } : entry))} rows={2} />
          </Field> : null}
        </div>
        {spec?.config_schema ? <SchemaFields schema={schema} value={formValue} onChange={updateForm} excluded={RESERVED_MODULE_FIELDS} /> : (
          <details><summary>{t('builder.rawModule')}</summary><JsonField value={item} onChange={(value) => {
            if (isObject(value)) onChange(items.map((entry, itemIndex) => itemIndex === index ? value : entry));
          }} /></details>
        )}
      </article>;
    })}
    <div className="toolbar extension-add-row">
      <select aria-label={t('builder.chooseModule')} value={selected} onChange={(event) => setSelected(event.target.value)}>
        <option value="">{t('builder.chooseModule')}</option>
        {candidates.map((module) => <option key={module.id} value={module.id}>{module.display_name} · {module.id}</option>)}
      </select>
      <Button variant="primary" onClick={add} disabled={!selected || (maxItems !== undefined && items.length >= maxItems)}>{t('builder.addModule')}</Button>
      {!candidates.length ? <span className="hint">{t('builder.noModules')}</span> : null}
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
  const [raw, setRaw] = useState(false);
  const [rawText, setRawText] = useState(() => JSON.stringify(config, null, 2));
  const body = pipelineOf(config);
  const pipelineSchema = pipeline.config_schema;
  useEffect(() => {
    if (!raw) setRawText(JSON.stringify(config, null, 2));
    setPreview(null);
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

  return <div className="extension-builder-content">
    <div className="extension-form-grid extension-pipeline-picker">
      <Field label={t('builder.pipelineType')}>
        <select value={String(body.pipeline_class || pipeline.config_id)} onChange={(event) => selectedPipeline(event.target.value)}>
          {catalog.pipelines.map((item) => <option key={item.id} value={item.config_id}>{item.display_name} · {item.config_id}</option>)}
        </select>
      </Field>
      {pipeline.description ? <p className="hint extension-description">{pipeline.description}</p> : null}
    </div>

    {!raw && pipeline.pipeline_id === 'PipelineSurveillance' ? <>
      {SURVEILLANCE_GROUPS.map((group) => {
        const moduleMap = isObject(body.modules) ? body.modules : {};
        const override = isObject(moduleMap[group.id]) ? moduleMap[group.id] : {};
        const mode = override.mode === 'replace' ? 'replace' : 'extend';
        const items = Array.isArray(override.items) ? override.items.filter(isObject) : [];
        const legacy = Array.isArray(body[group.id]) ? body[group.id].filter(isObject) : [];
        return <section className="extension-subpanel" key={group.id}>
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
          {mode === 'extend' && legacy.length ? <p className="hint">{t('builder.baseModules', { count: legacy.length })}</p> : null}
          {mode === 'replace' && legacy.length ? <p className="hint">{t('builder.replacedModules', { count: legacy.length })}</p> : null}
          <ModuleListEditor
            modules={catalog.modules}
            items={items}
            kind={group.kind}
            stage={group.id}
            title={t('builder.customModules')}
            onChange={(next) => changeGroup(group.id, next)}
          />
        </section>;
      })}
      <EventRulesEditor config={config} setConfig={setConfig} modules={catalog.modules} defaultEnabled={catalog.default_event_detectors} />
      <SchemaFields schema={pipelineSchema} value={body} onChange={changeBody}
        excluded={new Set([...SURVEILLANCE_GROUPS.map((group) => group.id), 'pipeline_class', 'modules'])} />
    </> : null}

    {!raw && pipeline.pipeline_id === 'PipelineDeclarative' ? <>
      <DeclarativeEditor body={body} changeBody={changeBody} modules={catalog.modules} />
      <EventRulesEditor config={config} setConfig={setConfig} modules={catalog.modules} defaultEnabled={catalog.default_event_detectors} />
    </> : null}
    {!raw && pipeline.pipeline_id === 'PipelineCapture' ? <ModuleListEditor
      modules={catalog.modules}
      items={(Array.isArray(body.sources) ? body.sources : []).filter(isObject)}
      kind="source"
      stage="capture-source"
      title={t('builder.sources')}
      maxItems={1}
      onChange={(sources) => changeBody({ ...body, sources })}
    /> : null}
    {!raw && !['PipelineSurveillance', 'PipelineDeclarative', 'PipelineCapture'].includes(pipeline.pipeline_id) ? (
      pipelineSchema ? <SchemaFields schema={pipelineSchema} value={body} onChange={changeBody} excluded={new Set(['pipeline_class'])} /> : (
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
    {preview ? <TopologyView preview={preview} /> : null}
  </div>;
}

function EventRulesEditor({ config, setConfig, modules, defaultEnabled }: { config: JsonObject; setConfig: (value: JsonObject) => void; modules: ExtensionModule[]; defaultEnabled: string[] }) {
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
  return <section className="extension-subpanel">
    <div className="extension-section-heading"><h3>{t('builder.eventBranch')}</h3><span className="hint">{t('builder.eventBranchHint')}</span></div>
    {items.map(([id, item]) => {
      const spec = candidates.find((module) => module.id === id || module.module_id === id || module.id === item.module_id);
      return <article key={id} className="extension-module-card">
        <div className="extension-module-heading">
          <label><input type="checkbox" checked={enabled.includes(id)} onChange={(event) => update({
            ...rules,
            enabled: event.target.checked ? [...enabled, id] : enabled.filter((name) => name !== id),
          })} /> <strong>{spec?.display_name || shortId(id)} <small>{id}</small></strong></label>
          {!defaultEnabled.includes(id) ? <Button size="sm" variant="danger" onClick={() => {
            const next = { ...rules };
            delete next[id];
            update({ ...next, enabled: enabled.filter((name) => name !== id) });
          }}>{t('builder.remove')}</Button> : null}
        </div>
        {spec?.config_schema ? <SchemaFields schema={spec.config_schema} value={item} onChange={(next) => update({ ...rules, [id]: { ...item, ...next } })} excluded={RESERVED_MODULE_FIELDS} /> : (
          <details><summary>{t('builder.rawModule')}</summary><JsonField value={item} onChange={(next) => { if (isObject(next)) update({ ...rules, [id]: next }); }} /></details>
        )}
      </article>;
    })}
    <div className="toolbar extension-add-row">
      <select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">{t('builder.chooseModule')}</option>
        {candidates.map((module) => <option key={module.id} value={module.id}>{module.display_name} · {module.id}</option>)}
      </select>
      <Button variant="primary" onClick={() => { add(selected); setSelected(''); }} disabled={!selected}>{t('builder.addRule')}</Button>
      {!candidates.length ? <span className="hint">{t('builder.noEventModules')}</span> : null}
    </div>
  </section>;
}

function DeclarativeEditor({ body, changeBody, modules }: { body: JsonObject; changeBody: (body: JsonObject) => void; modules: ExtensionModule[] }) {
  const { t } = useI18n();
  const stages = declarativeStages(body);
  const updateStages = (next: JsonObject[]) => changeBody({ ...body, stages: next });
  const move = (index: number, shift: number) => {
    const target = index + shift;
    if (target < 0 || target >= stages.length) return;
    const next = [...stages];
    [next[index], next[target]] = [next[target], next[index]];
    updateStages(next);
  };
  return <section className="extension-subpanel">
    <div className="extension-section-heading"><h3>{t('builder.linearStages')}</h3>
      <Button variant="primary" onClick={() => updateStages([...stages, { name: `stage_${stages.length + 1}`, kind: 'step', items: [] }])}>{t('builder.addStage')}</Button>
    </div>
    {stages.map((stage, index) => {
      const kind = ['source', 'frame', 'step'].includes(String(stage.kind)) ? String(stage.kind) : 'step';
      const moduleKind = kind === 'source' ? 'source' : 'processor_item';
      return <article className="extension-stage-card" key={`${String(stage.name)}-${index}`}>
        <div className="extension-stage-heading">
          <Field label={t('builder.stageName')}><input value={String(stage.name || '')} onChange={(event) => updateStages(stages.map((item, i) => i === index ? { ...item, name: event.target.value } : item))} /></Field>
          <Field label={t('builder.stageKind')}><select value={kind} onChange={(event) => updateStages(stages.map((item, i) => i === index ? { ...item, kind: event.target.value } : item))}>
            <option value="source">{t('builder.sourceStage')}</option><option value="frame">{t('builder.frameStage')}</option><option value="step">{t('builder.stepStage')}</option>
          </select></Field>
          <div className="toolbar">
            <Button size="sm" onClick={() => move(index, -1)} disabled={index === 0}>↑</Button>
            <Button size="sm" onClick={() => move(index, 1)} disabled={index === stages.length - 1}>↓</Button>
            <Button size="sm" variant="danger" onClick={() => updateStages(stages.filter((_, i) => i !== index))}>{t('builder.removeStage')}</Button>
          </div>
        </div>
        <ModuleListEditor modules={modules} items={(Array.isArray(stage.items) ? stage.items : []).filter(isObject)} kind={moduleKind} stage={kind}
          title={t('builder.stageModules')} onChange={(items) => updateStages(stages.map((item, i) => i === index ? { ...item, items } : item))} />
      </article>;
    })}
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

function PluginWorkshop({ catalog }: { catalog: ExtensionCatalog }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [template, setTemplate] = useState(catalog.templates[0]?.id || 'processor');
  const [operation, setOperation] = useState<PluginOperation | null>(null);
  const [recentOperations, setRecentOperations] = useState<PluginOperation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    void extensionsApi.operations().then((items) => {
      setRecentOperations(items);
      if (items.length) setOperation(items[0]);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);
  useEffect(() => {
    if (!operation || ['completed', 'pending_restart', 'dependencies_missing', 'failed'].includes(operation.status)) return;
    const timer = window.setInterval(() => {
      void extensionsApi.operation(operation.id).then((next) => {
        setOperation(next);
        setRecentOperations((items) => [next, ...items.filter((item) => item.id !== next.id)].slice(0, 20));
      }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [operation]);

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const created = await extensionsApi.createPlugin(name, template);
      setOperation(created);
      setRecentOperations((items) => [created, ...items.filter((item) => item.id !== created.id)].slice(0, 20));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  return <div className="extension-builder-content">
    <p className="hint">{t('builder.pluginHint')}</p>
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
    {recentOperations.length ? <section className="extension-panel extension-recent-operations">
      <h3>{t('builder.recentOperations')}</h3>
      <div className="toolbar">
        {recentOperations.map((item) => <Button key={item.id} variant={item.id === operation?.id ? 'primary' : 'outline'} onClick={() => setOperation(item)}>
          {item.name} · {t(`builder.status.${item.status}`)}
        </Button>)}
      </div>
    </section> : null}
    {operation ? <section className="extension-panel">
      <div className="extension-section-heading"><h3>{t('builder.operation')}</h3><span className={`extension-operation-state state-${operation.status}`}>{t(`builder.status.${operation.status}`)}</span></div>
      <p>{operation.message}</p>
      <dl className="extension-operation-details"><dt>{t('builder.pluginId')}</dt><dd><code>{operation.plugin_id}</code></dd>
        <dt>{t('builder.directory')}</dt><dd><code>{operation.directory}</code></dd>
      </dl>
      {operation.missing_dependencies?.length ? <p className="extension-warning">{t('builder.missingDependencies')}: {operation.missing_dependencies.join(', ')}</p> : null}
      {operation.archive ? <Button onClick={() => void extensionsApi.downloadArchive(operation.id, `evileye-plugin-${operation.name}.zip`)}>{t('builder.downloadZip')}</Button> : null}
      {operation.status === 'pending_restart' ? <p className="hint">{t('builder.pendingRestartHint')}</p> : null}
    </section> : null}
  </div>;
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
  const pipeline = useMemo(() => catalog?.pipelines.find((item) => item.config_id === pipelineId) || null, [catalog, pipelineId]);

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
    <header className="header"><div><h2>{t('builder.title')}</h2><p className="hint">{t('builder.hint')}</p></div></header>
    <div className="config-studio-tabs">
      <button className={`tab ${tab === 'pipeline' ? 'active' : ''}`} onClick={() => setTab('pipeline')}>{t('builder.pipelineTab')}</button>
      <button className={`tab ${tab === 'plugins' ? 'active' : ''}`} onClick={() => setTab('plugins')}>{t('builder.pluginsTab')}</button>
    </div>
    {error ? <div className="extension-alert extension-alert-error">{error}</div> : null}
    {notice ? <div className="extension-alert extension-alert-success">{notice}</div> : null}

    {tab === 'pipeline' ? <>
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
    </> : <section className="extension-panel"><PluginWorkshop catalog={catalog} /></section>}
  </div>;
}
