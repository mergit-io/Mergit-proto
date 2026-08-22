import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import type { TaskDetail } from "../lib/api";
import { AgentBadge } from "./AgentBadge";
import { StatusBadge } from "./StatusBadge";

interface Props {
  tasks: TaskDetail[];
}

function buildGraph(tasks: TaskDetail[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = tasks.map((t, i) => ({
    id: t.id,
    position: { x: 0, y: i * 120 },
    type: "default",
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    data: { label: <TaskNode task={t} /> },
    className: `bg-slab border ${t.status === "RUNNING" ? "border-violet" : "border-line"}`,
    style: {
      padding: 0,
      width: 220,
    },
  }));

  const edges: Edge[] = [];
  tasks.forEach((t) => {
    t.depends_on?.forEach?.((depId: string) => {
      edges.push({
        id: `${depId}->${t.id}`,
        source: depId,
        target: t.id,
        animated: t.status === "RUNNING",
      });
    });
  });

  return { nodes, edges };
}

function TaskNode({ task }: { task: TaskDetail }) {
  return (
    <div className="px-3 py-2.5 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <AgentBadge agent={task.agent_name} />
        <StatusBadge status={task.status} size="sm" />
      </div>
      <p className="font-mono text-xs text-dim leading-relaxed line-clamp-2">{task.description}</p>
    </div>
  );
}

export function TaskDAG({ tasks }: Props) {
  if (!tasks.length) return null;
  const { nodes, edges } = buildGraph(tasks);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        // Without a ceiling, a one-node graph is scaled up until the card fills the canvas.
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnDrag
        proOptions={{ hideAttribution: true }}
      >
        <Background color="rgb(var(--c-line-soft))" gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
