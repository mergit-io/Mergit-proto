import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useRef } from "react";
import type { SSEEvent } from "../lib/sse";

interface Props {
  events: SSEEvent[];
}

function formatEvent(e: SSEEvent): { label: string; text: string; cls: string } {
  const d = e.data;
  switch (e.event) {
    case "goal_status":
      return { label: "goal", text: `Status → ${d.status}`, cls: "text-blue-400" };
    case "task_update":
      return { label: d.agent as string ?? "task", text: `[${d.task_id}] ${d.status}`, cls: "text-sky-300" };
    case "task_done":
      return { label: "done", text: `[${d.task_id}] completed`, cls: "text-green-400" };
    case "task_waiting":
      return { label: "wait", text: `[${d.task_id}] waiting for webhook ${d.webhook_url}`, cls: "text-amber-400" };
    case "credential_request":
      return { label: "auth", text: `[${d.task_id}] needs ${d.provider || d.credential} — check banner below`, cls: "text-amber-300" };
    case "goal_done":
      return { label: "goal", text: `COMPLETED`, cls: "text-green-400 font-semibold" };
    case "tool_call":
      return { label: d.tool as string, text: `called with ${JSON.stringify(d.args).slice(0, 80)}`, cls: "text-violet-300" };
    case "tool_result":
      return { label: d.tool as string, text: `→ ${d.status}`, cls: "text-violet-400" };
    case "message":
      return { label: d.role as string, text: String(d.content).slice(0, 120), cls: "text-gray-300" };
    default:
      return { label: e.event, text: JSON.stringify(d).slice(0, 80), cls: "text-gray-500" };
  }
}

function ts() {
  return new Date().toLocaleTimeString("en", { hour12: false });
}

export function LiveLog({ events }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="h-full overflow-y-auto font-mono text-xs space-y-1 pr-1">
      <AnimatePresence initial={false}>
        {events
          .filter((e) => e.event !== "ping")
          .map((e, i) => {
            const { label, text, cls } = formatEvent(e);
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.15 }}
                className="flex gap-2 leading-relaxed"
              >
                <span className="text-text-muted shrink-0">{ts()}</span>
                <span className={`shrink-0 ${cls}`}>[{label}]</span>
                <span className="text-gray-400 break-all">{text}</span>
              </motion.div>
            );
          })}
      </AnimatePresence>
      {events.length === 0 && (
        <p className="text-text-muted italic">Waiting for events…</p>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
