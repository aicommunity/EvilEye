import { useEffect, useState } from 'react';
import { type ExtensionCatalog, type ExtensionModule } from '../../../api';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { ModuleListEditor } from './ModuleListEditor';
import { Field, type JsonObject, type SourceChoice, declarativeStages, isObject, parseEditorConfig, updatePipeline } from './shared';

export function DeclarativeEditor({ body, changeBody, modules, activeStage, onStageChange, focusModuleId, focusNodeId, sourceChoices }: {
  body: JsonObject;
  changeBody: (body: JsonObject) => void;
  modules: ExtensionModule[];
  activeStage: number;
  onStageChange: (index: number) => void;
  focusModuleId?: string;
  focusNodeId?: string;
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
          title={t('builder.stageModules')} focusModuleId={focusModuleId} focusNodeId={focusNodeId} focusStageIndex={index}
          sourceChoices={sourceChoices} onChange={(items) => updateStages(stages.map((item, i) => i === index ? { ...item, items } : item))} />
      </article>;
    })() : <p className="hint">{t('builder.noStages')}</p>}
    {pipelineSchemaFields(body) ? <p className="hint">{t('builder.finalResultsField')} <input value={String(body.final_results || '')} placeholder={t('builder.finalResultsPlaceholder')}
      onChange={(event) => changeBody({ ...body, final_results: event.target.value || undefined })} /></p> : null}
  </section>;
}

function pipelineSchemaFields(body: JsonObject): boolean {
  return Object.prototype.hasOwnProperty.call(body, 'final_results') || body.pipeline_class === 'PipelineDeclarative';
}

export function OpaqueConfigEditor({
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
