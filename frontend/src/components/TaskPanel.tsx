import { useState } from "react";
import type { TaskDetail } from "../lib/api";
import { AgentBadge } from "./AgentBadge";
import { StatusBadge } from "./StatusBadge";
import { Micro } from "./ui";

interface Props {
  task: TaskDetail;
}

export function TaskPanel({ task }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-line-soft last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-raise transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono text-dim w-3 shrink-0" aria-hidden="true">
            {open ? "−" : "+"}
          </span>
          <AgentBadge agent={task.agent_name} />
          <span className="text-sm text-text truncate">{task.description}</span>
        </div>
        <StatusBadge status={task.status} />
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 space-y-3 bg-raise">
          {Object.keys(task.inputs).length > 0 && (
            <div>
              <Micro className="block mb-1.5">Inputs</Micro>
              <pre className="font-mono text-xs bg-raise border border-line p-3 overflow-x-auto">
                {JSON.stringify(task.inputs, null, 2)}
              </pre>
            </div>
          )}

          {task.output && (
            <div>
              <Micro className="block mb-1.5">Output</Micro>
              <pre className="font-mono text-xs bg-raise border border-line p-3 overflow-x-auto max-h-48">
                {JSON.stringify(task.output, null, 2)}
              </pre>
            </div>
          )}

          {task.error && (
            <div>
              <Micro className="block mb-1.5">Error</Micro>
              <pre className="font-mono text-xs text-red bg-raise border border-line p-3 overflow-x-auto whitespace-pre-wrap">
                {task.error}
              </pre>
            </div>
          )}

          {task.wait_token && task.status === "WAITING_WEBHOOK" && (
            <div className="border border-amber p-3">
              <Micro className="block mb-1 text-amber">Waiting for webhook</Micro>
              <code className="font-mono text-xs text-amber">
                POST /api/webhooks/{task.wait_token}
              </code>
            </div>
          )}

          <p className="font-mono text-micro uppercase text-dim">Attempts: {task.attempt_count}</p>
        </div>
      )}
    </div>
  );
}
