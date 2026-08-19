import type { TaskDetail } from "../lib/api";
import { AgentBadge } from "./AgentBadge";

/**
 * The run, as the run actually is: an ordered pipeline of tasks with a line that fills as they
 * finish. Replaces an earlier 3D treatment that looked decorative without saying anything about
 * what the page was doing.
 */

const DONE = ["DONE", "COMPLETED"];
const RUNNING = ["RUNNING", "PLANNING", "NEW"];

function duration(task: TaskDetail): string | null {
  const secs = task.updated_at - task.created_at;
  if (!Number.isFinite(secs) || secs <= 0) return null;
  if (secs < 60) return `${Math.round(secs)}s`;
  const m = Math.floor(secs / 60);
  return `${m}m ${Math.round(secs % 60)}s`;
}

function toolCalls(task: TaskDetail): number | null {
  const output = task.output;
  if (!output || typeof output !== "object") return null;
  const calls = (output as Record<string, unknown>).tool_calls;
  return Array.isArray(calls) ? calls.length : null;
}

function nodeTone(status: string): { ring: string; fill: string; text: string } {
  if (DONE.includes(status)) return { ring: "border-proof/45", fill: "bg-[#E9F9F2]", text: "text-proof-deep" };
  if (RUNNING.includes(status)) return { ring: "border-accent/50", fill: "bg-[#F1EBFF]", text: "text-accent" };
  if (status === "FAILED") return { ring: "border-[#E86A5E]/45", fill: "bg-[#FFF1EF]", text: "text-[#C2453B]" };
  if (status === "WAITING_WEBHOOK") return { ring: "border-[#EAB308]/45", fill: "bg-[#FFF6E8]", text: "text-[#A16207]" };
  return { ring: "border-ink/12", fill: "bg-white", text: "text-ink-dim" };
}

interface Props {
  tasks: TaskDetail[];
  goalStatus: string;
  /** View switch, rendered inside the header row so it cannot overlap the summary. */
  action?: React.ReactNode;
}

export function RunPipeline({ tasks, goalStatus, action }: Props) {
  const done = tasks.filter((t) => DONE.includes(t.status)).length;
  const failed = tasks.filter((t) => t.status === "FAILED").length;
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  const total = tasks.reduce((acc, t) => {
    const s = t.updated_at - t.created_at;
    return acc + (Number.isFinite(s) && s > 0 ? s : 0);
  }, 0);

  return (
    <div className="mx-auto w-full max-w-[1400px] px-5 py-6 sm:px-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Run</p>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-ink-muted">
            <span>
              {done} of {tasks.length} done
            </span>
            {failed > 0 && <span className="text-[#C2453B]">{failed} failed</span>}
            {total > 0 && <span className="text-ink-dim">{Math.round(total)}s total</span>}
          </div>
          {action}
        </div>
      </div>

      {/* progress rail */}
      <div className="mb-6 h-1 w-full overflow-hidden rounded-full bg-ink/[0.07]">
        <div
          className={`h-1 rounded-full transition-[width] duration-500 ${
            failed > 0 ? "bg-[#E86A5E]" : "bg-gradient-to-r from-accent to-proof"
          }`}
          style={{ width: `${goalStatus === "FAILED" && pct === 0 ? 100 : pct}%` }}
        />
      </div>

      {/* steps */}
      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {tasks.map((task, i) => {
          const tone = nodeTone(task.status);
          const secs = duration(task);
          const calls = toolCalls(task);
          return (
            <li
              key={task.id}
              className={`relative flex flex-col gap-2.5 rounded-[18px] border bg-white p-4 ${tone.ring}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg font-mono text-[11px] font-semibold ${tone.fill} ${tone.text}`}
                  >
                    {i + 1}
                  </span>
                  <AgentBadge agent={task.agent_name} />
                </div>
                <span className={`shrink-0 font-mono text-[11px] ${tone.text}`}>
                  {DONE.includes(task.status)
                    ? "done"
                    : RUNNING.includes(task.status)
                      ? "running"
                      : task.status.toLowerCase().replace("_", " ")}
                </span>
              </div>

              <p className="line-clamp-2 text-[13px] leading-snug text-ink">{task.description}</p>

              <div className="mt-auto flex flex-wrap items-center gap-2 font-mono text-[11px] text-ink-dim">
                {secs && <span>{secs}</span>}
                {calls !== null && <span>· {calls} tool call{calls === 1 ? "" : "s"}</span>}
                {task.attempt_count > 1 && <span>· attempt {task.attempt_count}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
