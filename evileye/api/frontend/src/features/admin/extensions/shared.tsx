import { type ReactNode, useEffect, useState } from 'react';
import { type ExtensionModule, type ExtensionPipeline } from '../../../api';
import { useI18n } from '../../../i18n';
import { schemaDefaults } from '../schemaDefaults';
import { SchemaForm } from '../SchemaForm';

export type JsonObject = Record<string, any>;

export type BuilderTab = 'pipeline' | 'plugins';

type Schema = Record<string, any>;

export const SURVEILLANCE_GROUPS: Array<{ id: string; kind: string; title: string }> = [
  { id: 'sources', kind: 'source', title: 'builder.sources' },
  { id: 'preprocessors', kind: 'processor_item', title: 'builder.preprocessors' },
  { id: 'detectors', kind: 'processor_item', title: 'builder.detectors' },
  { id: 'trackers', kind: 'processor_item', title: 'builder.trackers' },
  { id: 'mc_trackers', kind: 'batch_processor', title: 'builder.multiTrackers' },
  { id: 'attributes_roi', kind: 'processor_item', title: 'builder.roiAttributes' },
  { id: 'attributes_classifier', kind: 'processor_item', title: 'builder.classifiers' },
];

export const RESERVED_MODULE_FIELDS = new Set([
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

export function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function pipelineOf(config: JsonObject): JsonObject {
  return isObject(config.pipeline) ? config.pipeline : config;
}

export function updatePipeline(config: JsonObject, update: (pipeline: JsonObject) => JsonObject): JsonObject {
  if (isObject(config.pipeline)) return { ...config, pipeline: update(config.pipeline) };
  return update(config);
}

export function newConfig(pipeline: ExtensionPipeline): JsonObject {
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

export function moduleCandidates(modules: ExtensionModule[], kind: string, stage: string): ExtensionModule[] {
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

export function moduleOptionLabel(module: ExtensionModule, translate: (key: string) => string): string {
  const marker = module.plugin_id === 'evileye' ? '' : `${translate('builder.pluginMarker')} · `;
  return `${marker}${module.display_name} · ${module.id}`;
}

export function moduleDefaults(module: ExtensionModule, sourceId = 0): JsonObject {
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

export type SourceChoice = { id: number; label: string };

export function pipelineSources(body: JsonObject): SourceChoice[] {
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

export function SourceIdsField({ value, choices, onChange, label }: {
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

export function declarativeStages(body: JsonObject): JsonObject[] {
  if (Array.isArray(body.stages) && body.stages.length) return body.stages.filter(isObject);
  return LEGACY_DECLARATIVE_STAGES.flatMap(([name, kind]) => {
    const items = body[name];
    return Array.isArray(items) && items.length ? [{ name, kind, items: items.filter(isObject) }] : [];
  });
}

export function shortId(moduleId: unknown): string {
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

export function jsonDiff(before: unknown, after: unknown, path = '$'): string[] {
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

export function parseEditorConfig(raw: string): JsonObject {
  const parsed: unknown = JSON.parse(raw);
  if (!isObject(parsed)) throw new Error('JSON root must be an object');
  return parsed;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="extension-field"><span>{label}</span>{children}{hint ? <small>{hint}</small> : null}</label>;
}

export function JsonField({ value, onChange, rows = 3 }: { value: unknown; onChange: (value: unknown) => void; rows?: number }) {
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

export function SchemaFields({
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
