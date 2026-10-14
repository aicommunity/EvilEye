import { createElement, type MouseEvent as ReactMouseEvent } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PipelinePreview } from '../../api';
import { I18nProvider } from '../../i18n';
import { PipelineGraph } from './PipelineGraph';

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ nodes, onNodeClick, nodesDraggable, nodesConnectable }: any) => createElement('div', {
    'data-testid': 'react-flow',
    'data-draggable': String(nodesDraggable),
    'data-connectable': String(nodesConnectable),
  }, nodes.map((node: any) => createElement('button', {
    key: node.id,
    'aria-label': node.ariaLabel,
    onClick: (event: ReactMouseEvent) => onNodeClick(event, node),
  }, node.data.label))),
  Background: () => null,
  Controls: () => null,
}));

const preview: PipelinePreview = {
  valid: true,
  errors: [],
  warnings: [],
  topology: {
    pipeline_id: 'PipelineSurveillance',
    title: 'Surveillance',
    description: 'Sources flow through detectors.',
    nodes: [
      { node_id: 'detectors:0:acme/person-detector', label: 'Person detector', kind: 'processor_item', stage: 'detectors', module_id: 'acme/person-detector', status: 'unknown' },
    ],
    edges: [],
  },
};

describe('PipelineGraph', () => {
  it('selects a declared module and disables arbitrary dragging and connections', () => {
    const onSelect = vi.fn();
    render(<I18nProvider><PipelineGraph preview={preview} onSelect={onSelect} /></I18nProvider>);

    fireEvent.click(screen.getByRole('button', { name: /Person detector, detectors, unknown/ }));
    expect(onSelect).toHaveBeenCalledWith(preview.topology.nodes[0]);
    expect(screen.getByTestId('react-flow').getAttribute('data-draggable')).toBe('false');
    expect(screen.getByTestId('react-flow').getAttribute('data-connectable')).toBe('false');
  });
});
