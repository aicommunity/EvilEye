import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import type { ExtensionModule } from '../../api';
import { DeclarativeEditor, ModuleListEditor } from './ExtensionsPage';

const module: ExtensionModule = {
  id: 'acme/person-detector',
  module_id: 'person-detector',
  plugin_id: 'acme',
  kind: 'processor_item',
  display_name: 'Person detector',
  description: 'Example detector',
  stages: ['detectors'],
  execution_modes: ['thread', 'process'],
  default_execution_mode: 'thread',
  capabilities: [],
  config_schema: {
    type: 'object',
    properties: { threshold: { type: 'number', default: 0.4 } },
  },
};

describe('ModuleListEditor', () => {
  it('selects one module inspector and edits source assignment as a camera list', () => {
    const onChange = vi.fn();
    render(<I18nProvider><ModuleListEditor
      modules={[module]}
      items={[{ module_id: module.id, enable: true, execution_mode: 'thread', threshold: 0.4 }]}
      kind="processor_item"
      stage="detectors"
      title="Detectors"
      sourceChoices={[{ id: 7, label: 'North camera' }, { id: 9, label: 'South camera' }]}
      onChange={onChange}
    /></I18nProvider>);

    expect(screen.getAllByText('Person detector').length).toBeGreaterThan(0);
    const southCamera = screen.getByLabelText(/South camera/) as HTMLInputElement;
    fireEvent.click(southCamera);
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ module_id: module.id, source_ids: [9] }),
    ]);
  });

  it('selects the exact duplicate module instance identified by the graph node', () => {
    const duplicateItems = [
      { module_id: module.id, threshold: 0.3 },
      { module_id: module.id, threshold: 0.8 },
    ];
    render(<I18nProvider><ModuleListEditor
      modules={[module]}
      items={duplicateItems}
      kind="processor_item"
      stage="detectors"
      title="Detectors"
      focusNodeId={'detectors:1:' + module.id}
      focusModuleId={module.id}
      onChange={() => undefined}
    /></I18nProvider>);

    expect((screen.getByLabelText('threshold') as HTMLInputElement).value).toBe('0.8');
  });

  it('does not map a base graph node onto a same-ID extension module', () => {
    const tracker: ExtensionModule = { ...module, id: 'acme/tracker', module_id: 'tracker', display_name: 'Tracker' };
    render(<I18nProvider><ModuleListEditor
      modules={[module, tracker]}
      items={[{ module_id: tracker.id, threshold: 0.1 }, { module_id: module.id, threshold: 0.8 }]}
      kind="processor_item"
      stage="detectors"
      title="Additional detectors"
      focusNodeId={'detectors:1:' + module.id}
      focusModuleId={module.id}
      nodeIndexOffset={2}
      onChange={() => undefined}
    /></I18nProvider>);

    expect(screen.getByRole('article').querySelector('strong')?.textContent).toBe('Tracker');
  });

  it('shows module-specific fields only for the selected list item', () => {
    const other: ExtensionModule = { ...module, id: 'acme/tracker', module_id: 'tracker', display_name: 'Tracker' };
    render(<I18nProvider><ModuleListEditor
      modules={[module, other]}
      items={[{ module_id: module.id, threshold: 0.4 }, { module_id: other.id, threshold: 0.8 }]}
      kind="processor_item"
      stage="detectors"
      title="Modules"
      onChange={() => undefined}
    /></I18nProvider>);

    expect(screen.getAllByText('Person detector').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Tracker/ }));
    expect(screen.getByRole('article').querySelector('strong')?.textContent).toBe('Tracker');
    expect((screen.getByLabelText('threshold') as HTMLInputElement).value).toBe('0.8');
  });
});

describe('DeclarativeEditor', () => {
  it('uses accessible stage tabs and supports arrow-key navigation', () => {
    const onStageChange = vi.fn();
    const props = {
      body: {
        pipeline_class: 'PipelineDeclarative',
        stages: [
          { name: 'input', kind: 'source', items: [] },
          { name: 'detect', kind: 'step', items: [{ module_id: module.id }] },
        ],
      },
      changeBody: vi.fn(),
      modules: [module],
      sourceChoices: [],
      onStageChange,
    };
    const view = render(<I18nProvider><DeclarativeEditor {...props} activeStage={0} /></I18nProvider>);

    const tabs = screen.getAllByRole('tab');
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(tabs[1].getAttribute('tabindex')).toBe('-1');
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' });
    expect(onStageChange).toHaveBeenCalledWith(1);

    view.rerender(<I18nProvider><DeclarativeEditor {...props} activeStage={1} /></I18nProvider>);
    expect(screen.getByRole('tab', { name: 'detect' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe('declarative-stage-tab-1');
  });
});
