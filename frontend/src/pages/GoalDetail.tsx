import { motion } from "framer-motion";
import { ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { LiveLog } from "../components/LiveLog";
import { OutputDisplay } from "../components/OutputDisplay";
import { StatusBadge } from "../components/StatusBadge";
import { TaskDAG } from "../components/TaskDAG";
import { TaskPanel } from "../components/TaskPanel";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { ModelErrorBanner } from "../components/ModelErrorBanner";
import { api } from "../lib/api";
import { useSSE } from "../lib/sse";

const ACTIVE_STATUSES = new Set(["NEW", "PLANNING", "RUNNING"]);

function fetcher(id: string) {
  return api.getGoal(id);
}

export function GoalDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { data, isLoading, error } = useSWR(
    id ? `/api/goals/${id}` : null,
    () => fetcher(id!),
    { refreshInterval: (data) => (data && ACTIVE_STATUSES.has(data.status) ? 2000 : 0) }
  );

  const isActive = data ? ACTIVE_STATUSES.has(data.status) : false;
  const sseEvents = useSSE(id, isActive);

  if (isLoading) {
    return (
      <div className="relative min-h-screen" style={{ background: "#000" }}>
        <AppBackground />
        <div className="relative z-10 flex flex-col min-h-screen">
          <AppNav />
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-2.5 text-text-muted">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading goal…</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="relative min-h-screen" style={{ background: "#000" }}>
        <AppBackground />
        <div className="relative z-10 flex flex-col min-h-screen">
          <AppNav />
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-center">
              <AlertCircle className="w-8 h-8 text-danger/70" />
              <p className="text-sm text-text-muted">
                {error ? `Error: ${error.message}` : "Goal not found."}
              </p>
              <button
                onClick={() => nav("/app")}
                className="text-xs text-accent hover:text-accent/80 transition-colors"
              >
                ← Back to Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const tasks = data.tasks ?? [];

  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
      <AppNav />

      {/* Goal header */}
      <div className="border-b border-white/6 bg-black/40 backdrop-blur-md">
        <div className="max-w-none px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => nav("/app")}
            className="flex items-center gap-1.5 text-text-muted hover:text-white text-xs font-medium transition-colors shrink-0"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Dashboard
          </button>
          <div className="w-px h-4 bg-white/10" />
          <p className="flex-1 min-w-0 truncate text-sm font-medium text-gray-200">{data.title}</p>
          <StatusBadge status={data.status} />
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left: DAG + Tasks */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-white/8 bg-black/20 backdrop-blur-sm">
          {/* DAG */}
          {tasks.length > 0 && (
            <div className="h-64 lg:h-80 border-b border-white/6">
              <TaskDAG tasks={tasks} />
            </div>
          )}

          {/* Tasks */}
          <div className="flex-1 overflow-y-auto p-5 space-y-2">
            <div className="flex items-center gap-2 mb-4">
              <p className="text-xs text-text-muted uppercase tracking-widest font-semibold">
                Tasks
              </p>
              {tasks.length > 0 && (
                <span className="px-1.5 py-0.5 rounded-md bg-white/6 text-xs text-text-muted">
                  {tasks.length}
                </span>
              )}
            </div>

            {tasks.length === 0 && (
              <div className="flex items-center gap-2 text-text-muted text-sm py-4">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Orchestrator is planning tasks…</span>
              </div>
            )}

            {tasks.map((t) => (
              <TaskPanel key={t.id} task={t} />
            ))}

            {/* Output */}
            {data.output && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-5"
              >
                <p className="text-xs text-text-muted uppercase tracking-widest font-semibold mb-3">
                  Output
                </p>
                <OutputDisplay output={data.output} />
              </motion.div>
            )}

            {/* Error */}
            {data.error && (
              <div className="rounded-xl border border-danger/30 bg-danger/5 p-4 mt-4">
                <div className="flex items-center gap-2 mb-1">
                  <AlertCircle className="w-4 h-4 text-danger" />
                  <p className="text-sm text-red-400 font-semibold">Goal Failed</p>
                </div>
                <p className="text-xs text-red-300 font-mono leading-relaxed">{data.error}</p>
              </div>
            )}

            {/* Model error toast */}
            {data.error && <ModelErrorBanner error={data.error} />}
          </div>
        </div>

        {/* Right: Live Log */}
        <div className="w-full lg:w-96 flex flex-col border-t lg:border-t-0 border-white/8 bg-black/30 backdrop-blur-sm">
          <div className="border-b border-white/6 px-5 py-3 flex items-center justify-between">
            <p className="text-xs text-text-muted uppercase tracking-widest font-semibold">
              Live Log
            </p>
            {isActive && (
              <span className="flex items-center gap-1.5 text-xs text-accent">
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
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
    </div>
  );
}
