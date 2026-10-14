import { useMemo } from 'react';
import { Background, Controls, ReactFlow, type Edge, type Node, type NodeMouseHandler } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { PipelinePreview } from '../../api';
import { useI18n } from '../../i18n';

type GraphNode = PipelinePreview['topology']['nodes'][number];

export function PipelineGraph({ preview, onSelect }: { preview: PipelinePreview; onSelect?: (node: GraphNode) => void }) {
  const { t } = useI18n();
  const nodes = useMemo<Node[]>(() => {
    const stageOrder = [...new Set(preview.topology.nodes.map((node) => node.stage))];
    const stageIndices = new Map(stageOrder.map((stage, index) => [stage, index]));
    const offsets = new Map<string, number>();
    return preview.topology.nodes.map((node) => {
      const itemIndex = offsets.get(node.stage) || 0;
      offsets.set(node.stage, itemIndex + 1);
      const eventBranch = /event|alarm/i.test(`${node.stage} ${node.kind}`);
      const x = (stageIndices.get(node.stage) || 0) * 230;
      const y = (eventBranch ? 420 : 30) + itemIndex * 112;
      return {
        id: node.node_id,
        position: { x, y },
        data: { label: <div className="pipeline-graph-node-content"><strong>{node.label}</strong><small>{node.stage} · {node.status || 'unknown'}</small></div> },
        ariaLabel: `${node.label}, ${node.stage}, ${node.status || 'unknown'}${node.module_id ? `, ${node.module_id}` : ''}`,
        title: node.module_id || node.label,
        className: `pipeline-graph-node ${eventBranch ? 'is-event' : ''}`,
        style: { width: 190, minHeight: 72 },
        focusable: true,
        selectable: true,
      };
    });
  }, [preview.topology.nodes]);
  const edges = useMemo<Edge[]>(() => preview.topology.edges.map((edge, index) => ({
    id: `${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
    type: 'smoothstep',
    animated: false,
    focusable: true,
    selectable: true,
  })), [preview.topology.edges]);
  const handleNodeClick: NodeMouseHandler = (_event, node) => {
    const selected = preview.topology.nodes.find((item) => item.node_id === node.id);
    if (selected) onSelect?.(selected);
  };

  return <div className="pipeline-graph" role="region" aria-label={t('builder.pipelineTopology')}>
    {nodes.length ? <ReactFlow
      nodes={nodes}
      edges={edges}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      nodesConnectable={false}
      nodesDraggable={false}
      elementsSelectable
      deleteKeyCode={null}
      onNodeClick={handleNodeClick}
      proOptions={{ hideAttribution: true }}
      minZoom={0.25}
      maxZoom={1.5}
    >
      <Background color="var(--border)" gap={22} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow> : <p className="hint">{t('builder.emptyTopology')}</p>}
  </div>;
}
