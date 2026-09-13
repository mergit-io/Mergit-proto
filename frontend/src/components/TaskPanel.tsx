import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { TaskDetail } from "../lib/api";
import { AgentBadge } from "./AgentBadge";
import { StatusBadge } from "./StatusBadge";

interface Props {
  task: TaskDetail;
}

export function TaskPanel({ task }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface hover:bg-white/[0.02] transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          {open ? <ChevronDown className="w-4 h-4 text-text-muted shrink-0" /> : <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />}
          <AgentBadge agent={task.agent_name} />
          <span className="text-sm text-gray-200 truncate">{task.description}</span>
        </div>
        <StatusBadge status={task.status} size="sm" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-2 space-y-3 border-t border-border bg-black/20">
              {/* Inputs */}
              {Object.keys(task.inputs).length > 0 && (
                <div>
                  <p className="text-xs text-text-muted mb-1 font-medium uppercase tracking-wider">Inputs</p>
                  <pre className="text-xs text-gray-300 bg-black/30 rounded-lg p-3 overflow-x-auto">
                    {JSON.stringify(task.inputs, null, 2)}
                  </pre>
                </div>
              )}

              {/* Output */}
              {task.output && (
                <div>
                  <p className="text-xs text-text-muted mb-1 font-medium uppercase tracking-wider">Output</p>
                  <pre className="text-xs text-gray-300 bg-black/30 rounded-lg p-3 overflow-x-auto max-h-48">
                    {JSON.stringify(task.output, null, 2)}
                  </pre>
                </div>
              )}

              {/* Error */}
              {task.error && (
                <div>
                  <p className="text-xs text-text-muted mb-1 font-medium uppercase tracking-wider">Error</p>
                  <p className="text-xs text-red-400 bg-red-400/5 rounded-lg p-3">{task.error}</p>
                </div>
              )}

              {/* Webhook waiting */}
              {task.wait_token && task.status === "WAITING_WEBHOOK" && (
                <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-3">
                  <p className="text-xs text-amber-300 font-medium mb-1">Waiting for webhook</p>
                  <code className="text-xs text-amber-200">
                    POST /api/webhooks/{task.wait_token}
                  </code>
                </div>
              )}

              <p className="text-xs text-text-muted">Attempts: {task.attempt_count}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
