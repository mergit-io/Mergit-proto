import { useEffect, useRef } from "react";
import type { SSEEvent } from "../lib/sse";
import { toneOf } from "./ui";

interface Props {
  events: SSEEvent[];
}

function toneClass(tone: ReturnType<typeof toneOf>) {
  switch (tone) {
    case "run":
      return "text-violet";
    case "done":
      return "text-mint";
    case "fail":
      return "text-red";
    case "wait":
      return "text-amber";
    default:
      return "text-dim";
  }
}

function formatEvent(e: SSEEvent): { label: string; text: string; cls: string } {
  const d = e.data;
  switch (e.event) {
    case "goal_status":
      return { label: "goal", text: `Status → ${d.status}`, cls: toneClass(toneOf(String(d.status ?? ""))) };
    case "task_update":
      return {
        label: (d.agent as string) ?? "task",
        text: `[${d.task_id}] ${d.status}`,
        cls: toneClass(toneOf(String(d.status ?? ""))),
      };
    case "task_done":
      return { label: "done", text: `[${d.task_id}] completed`, cls: toneClass("done") };
    case "task_waiting":
      return { label: "wait", text: `[${d.task_id}] waiting for webhook ${d.webhook_url}`, cls: toneClass("wait") };
    case "credential_request":
      return {
        label: "auth",
        text: `[${d.task_id}] needs ${d.provider || d.credential} — check banner below`,
        cls: toneClass("wait"),
      };
    case "goal_done":
      return { label: "goal", text: `COMPLETED`, cls: toneClass("done") };
    case "tool_call":
      return { label: d.tool as string, text: `called with ${JSON.stringify(d.args).slice(0, 80)}`, cls: "text-dim" };
    case "tool_result":
      return { label: d.tool as string, text: `→ ${d.status}`, cls: "text-dim" };
    case "message":
      return { label: d.role as string, text: String(d.content).slice(0, 120), cls: "text-dim" };
    default:
      return { label: e.event, text: JSON.stringify(d).slice(0, 80), cls: "text-dim" };
  }
}

/** Events carry their own unix-second `ts`. Reading the clock at render time
    instead stamped every row with the same moment, which made the transcript
    useless for seeing how long a step actually took. */
function stamp(e: SSEEvent): string {
  const raw = e.data?.ts;
  const d = typeof raw === "number" ? new Date(raw * 1000) : new Date();
  return d.toLocaleTimeString("en", { hour12: false });
}

export function LiveLog({ events }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const visible = events.filter((e) => e.event !== "ping");

  return (
    <div className="h-full overflow-y-auto font-mono text-xs">
      {visible.map((e, i) => {
        const { label, text, cls } = formatEvent(e);
        return (
          <div key={i} className="flex gap-3 py-0.5 leading-relaxed">
            <span className="text-dim shrink-0 tabular">{stamp(e)}</span>
            <span className={`shrink-0 text-micro uppercase ${cls}`}>[{label}]</span>
            <span className="text-text break-all">{text}</span>
          </div>
        );
      })}
      {visible.length === 0 && (
        <p className="micro">No events yet</p>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
