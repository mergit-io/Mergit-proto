import { motion } from "framer-motion";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { LiveLog } from "../components/LiveLog";
import { OutputDisplay } from "../components/OutputDisplay";
import { StatusBadge } from "../components/StatusBadge";
import { TaskDAG } from "../components/TaskDAG";
import { TaskPanel } from "../components/TaskPanel";
import { api } from "../lib/api";
import { useSSE } from "../lib/sse";

const ACTIVE_STATUSES = new Set(["NEW", "PLANNING", "RUNNING"]);

function fetcher(id: string) {
  return api.getGoal(id);
}

export function GoalDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { data, isLoading } = useSWR(
    id ? `/api/goals/${id}` : null,
    () => fetcher(id!),
    { refreshInterval: (data) => (data && ACTIVE_STATUSES.has(data.status) ? 2000 : 0) }
  );

  const isActive = data ? ACTIVE_STATUSES.has(data.status) : false;
  const sseEvents = useSSE(id, isActive);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <RefreshCw className="w-5 h-5 text-text-muted animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-text-muted text-sm">Goal not found.</p>
      </div>
    );
  }

  const tasks = data.tasks ?? [];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <nav className="border-b border-border px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => nav("/app")}
          className="flex items-center gap-1.5 text-text-muted hover:text-white text-sm transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Dashboard
        </button>
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-medium text-gray-100">{data.title}</p>
        </div>
        <StatusBadge status={data.status} />
      </nav>

      {/* Body */}
      <div className="flex-1 flex flex-col lg:flex-row gap-0 overflow-hidden">
        {/* Left: DAG + Tasks */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-border">
          {/* DAG */}
          {tasks.length > 0 && (
            <div className="h-64 lg:h-80 border-b border-border">
              <TaskDAG tasks={tasks} />
            </div>
          )}

          {/* Tasks */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            <p className="text-xs text-text-muted uppercase tracking-wider font-medium mb-3">
              Tasks {tasks.length > 0 ? `(${tasks.length})` : ""}
            </p>

            {tasks.length === 0 && (
              <div className="flex items-center gap-2 text-text-muted text-sm">
                <RefreshCw className="w-4 h-4 animate-spin" />
                Planning…
              </div>
            )}

            {tasks.map((t) => (
              <TaskPanel key={t.id} task={t} />
            ))}

            {/* Output */}
            {data.output && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
                <p className="text-xs text-text-muted uppercase tracking-wider font-medium mb-2">Output</p>
                <OutputDisplay output={data.output} />
              </motion.div>
            )}

            {data.error && (
              <div className="rounded-xl border border-danger/30 bg-danger/5 p-4 mt-4">
                <p className="text-sm text-red-400 font-medium">Failed</p>
                <p className="text-xs text-red-300 mt-1">{data.error}</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: Live Log */}
        <div className="w-full lg:w-96 flex flex-col border-t lg:border-t-0 border-border">
          <div className="border-b border-border px-4 py-3 flex items-center justify-between">
            <p className="text-xs text-text-muted uppercase tracking-wider font-medium">Live Log</p>
            {isActive && (
              <span className="flex items-center gap-1.5 text-xs text-blue-400">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                Streaming
              </span>
            )}
          </div>
          <div className="flex-1 overflow-hidden p-4">
            <LiveLog events={sseEvents} />
          </div>
        </div>
      </div>
    </div>
  );
}
