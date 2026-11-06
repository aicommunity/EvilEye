import { useEffect, useState } from 'react';
import { type ExtensionModule } from '../../../api';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { Field, JsonField, type JsonObject, RESERVED_MODULE_FIELDS, SchemaFields, type SourceChoice, SourceIdsField, isObject, moduleCandidates, moduleDefaults, moduleOptionLabel, shortId } from './shared';

export function ModuleListEditor({
  modules,
  items,
  kind,
  stage,
  title,
  onChange,
  maxItems,
  focusModuleId,
  focusNodeId,
  focusStageIndex,
  nodeIndexOffset = 0,
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
  focusNodeId?: string;
  focusStageIndex?: number;
  nodeIndexOffset?: number;
  allowAdd?: boolean;
  sourceChoices?: SourceChoice[];
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const candidates = moduleCandidates(modules, kind, stage);
  useEffect(() => {
    let index = -1;
    let nodeTargetsThisList = false;
    if (focusNodeId) {
      const parts = focusNodeId.split(':');
      if (focusStageIndex !== undefined && parts[0] === 'stage' && Number(parts[1]) === focusStageIndex) {
        nodeTargetsThisList = true;
        index = Number(parts[2]);
      } else if (/^\d+$/.test(parts[1] || '') &&
          (parts[0] === stage || (stage === 'capture-source' && parts[0] === 'sources'))) {
        nodeTargetsThisList = true;
        index = Number(parts[1]) - nodeIndexOffset;
      }
    }
    if (!nodeTargetsThisList) {
      index = focusModuleId
        ? items.findIndex((item) => String(item.module_id || item.type || '') === focusModuleId)
        : -1;
    }
    if (Number.isInteger(index) && index >= 0 && index < items.length) setActiveIndex(index);
  }, [focusNodeId, focusStageIndex, nodeIndexOffset, focusModuleId, items, stage]);
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
