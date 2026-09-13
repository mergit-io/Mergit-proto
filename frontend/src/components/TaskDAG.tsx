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

const STATUS_EDGE_COLOR: Record<string, string> = {
  DONE: "#22c55e",
  RUNNING: "#3b82f6",
  FAILED: "#ef4444",
  WAITING_WEBHOOK: "#f59e0b",
};

function buildGraph(tasks: TaskDetail[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = tasks.map((t, i) => ({
    id: t.id,
    position: { x: 0, y: i * 120 },
    type: "default",
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    data: { label: <TaskNode task={t} /> },
    style: {
      background: "#111111",
      border: `1px solid ${STATUS_EDGE_COLOR[t.status] ?? "#1f1f1f"}`,
      borderRadius: 12,
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
        style: { stroke: STATUS_EDGE_COLOR[t.status] ?? "#3a3a3a" },
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
      <p className="text-xs text-gray-300 leading-relaxed line-clamp-2">{task.description}</p>
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
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnDrag
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1f1f1f" gap={20} size={1} />
        <Controls showInteractive={false} className="!bg-surface !border-border" />
      </ReactFlow>
    </div>
  );
}
