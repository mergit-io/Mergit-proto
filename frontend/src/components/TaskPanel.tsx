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
    <div className="overflow-hidden rounded-[18px] border border-ink/[0.09] bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-paper-2"
      >
        <div className="flex items-center gap-3 min-w-0">
          {open ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-dim" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-dim" />}
          <AgentBadge agent={task.agent_name} />
          <span className="truncate text-sm text-ink">{task.description}</span>
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
            <div className="space-y-3 border-t border-ink/[0.07] bg-paper-2/60 px-5 pb-5 pt-3">
              {/* Inputs */}
              {Object.keys(task.inputs).length > 0 && (
                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-dim">Inputs</p>
                  <pre className="overflow-x-auto rounded-xl border border-ink/[0.07] bg-white p-3 font-mono text-[11px] text-ink-muted">
                    {JSON.stringify(task.inputs, null, 2)}
                  </pre>
                </div>
              )}

              {/* Output */}
              {task.output && (
                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-dim">Output</p>
                  <pre className="max-h-48 overflow-x-auto rounded-xl border border-ink/[0.07] bg-white p-3 font-mono text-[11px] text-ink-muted">
                    {JSON.stringify(task.output, null, 2)}
                  </pre>
                </div>
              )}

              {/* Error */}
              {task.error && (
                <div>
                  <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-dim">Error</p>
                  <p className="rounded-xl border border-[#E86A5E]/25 bg-[#FFF1EF] p-3 font-mono text-[11px] leading-relaxed text-[#C2453B]">{task.error}</p>
                </div>
              )}

              {/* Webhook waiting */}
              {task.wait_token && task.status === "WAITING_WEBHOOK" && (
                <div className="rounded-xl border border-[#EAB308]/30 bg-[#FFF6E8] p-3">
                  <p className="mb-1 text-xs font-semibold text-[#A16207]">Waiting for webhook</p>
                  <code className="font-mono text-[11px] text-[#A16207]">
                    POST /api/webhooks/{task.wait_token}
                  </code>
                </div>
              )}

              <p className="font-mono text-[11px] text-ink-dim">Attempts: {task.attempt_count}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
