import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import useSWR from "swr";
import { LiveLog } from "../components/LiveLog";
import { OutputDisplay } from "../components/OutputDisplay";
import { StatusBadge } from "../components/StatusBadge";
import { TaskDAG } from "../components/TaskDAG";
import { TaskPanel } from "../components/TaskPanel";
import { AppNav } from "../components/AppNav";
import { ModelErrorBanner } from "../components/ModelErrorBanner";
import { Empty, Loading, Micro, Notice, Status, toneOf } from "../components/ui";
import { api } from "../lib/api";
import { useSSE } from "../lib/sse";

const ACTIVE_STATUSES = new Set(["NEW", "PLANNING", "RUNNING"]);

interface CredentialRequest {
  task_id: string;
  credential: string;
  provider: string;
  message: string;
}

/** An agent has paused for a key it does not have. Saving it resumes the task. */
function CredentialBanner({ req, onDismiss }: { req: CredentialRequest; onDismiss: () => void }) {
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    if (!value.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      await api.updateApiKey(req.provider, value.trim());
      onDismiss();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "The key could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-l-2 border-amber border-y border-r border-line bg-slab p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Micro>Waiting on a key</Micro>
          <p className="text-sm text-amber mt-1.5">{req.message}</p>
        </div>
        <button onClick={onDismiss} aria-label="Dismiss" className="micro hover:text-text shrink-0">
          ✕
        </button>
      </div>

      <div className="flex items-center gap-px mt-3">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder={`Paste ${req.credential}`}
          autoFocus
          className="field flex-1 font-mono text-xs"
        />
        <button onClick={() => setShow((s) => !s)} className="btn-ghost">
          {show ? "Hide" : "Show"}
        </button>
        <button onClick={save} disabled={saving || !value.trim()} className="btn-primary">
          {saving ? "Saving…" : "Save and resume"}
        </button>
      </div>

      {err && <p className="text-xs text-red mt-2">{err}</p>}
    </div>
  );
}

function Rail({
  goalText,
  tasks,
  tools,
  live,
  watched,
}: {
  goalText: string;
  tasks: { id: string; agent_name: string; status: string }[];
  tools: string[];
  live: boolean;
  /** True once this page has actually received stream events for the run. */
  watched: boolean;
}) {
  return (
    <aside className="w-full lg:w-72 shrink-0 border-b lg:border-b-0 lg:border-r border-line">
      <div className="px-4 py-4 border-b border-line">
        <Micro>Goal</Micro>
        <p className="text-sm mt-2 leading-snug">{goalText}</p>
      </div>

      <div className="border-b border-line">
        <div className="px-4 py-2.5 border-b border-line">
          <Micro>Swarm</Micro>
        </div>
        {tasks.length === 0 ? (
          <p className="px-4 py-3 text-xs text-dim">Waiting on the plan.</p>
        ) : (
          <ul>
            {tasks.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between px-4 py-2 border-b border-line-soft last:border-0"
              >
                <span className="font-mono text-micro uppercase">{t.agent_name}</span>
                <Status status={t.status} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="px-4 py-2.5 border-b border-line">
          <Micro>Tools seen live</Micro>
        </div>
        {tools.length === 0 ? (
          // Tool calls arrive only on the event stream, which has no replay: anything
          // that fired before this page connected is not recoverable from the API.
          // Saying "nothing was called" would be a claim the page cannot support.
          <p className="px-4 py-3 text-xs text-dim leading-relaxed">
            {live || watched
              ? "Calls appear here as agents make them. Anything from before this page opened is not shown."
              : "This run finished before the page opened, so its calls were not captured."}
          </p>
        ) : (
          <ul className="px-4 py-3 flex flex-wrap gap-x-3 gap-y-1.5">
            {tools.map((t) => (
              <li key={t} className="font-mono text-xs text-dim">
                {t}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

export function GoalDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useSWR(
    id ? `/api/goals/${id}` : null,
    () => api.getGoal(id!),
    { refreshInterval: (d) => (d && ACTIVE_STATUSES.has(d.status) ? 2000 : 0) }
  );

  const isActive = data ? ACTIVE_STATUSES.has(data.status) : false;
  const sseEvents = useSSE(id, isActive);

  const [credRequest, setCredRequest] = useState<CredentialRequest | null>(null);

  useEffect(() => {
    const last = [...sseEvents].reverse().find((e) => e.event === "credential_request");
    if (last) setCredRequest(last.data as unknown as CredentialRequest);
  }, [sseEvents]);

  // The tool names this run has actually reached for, in first-seen order.
  const tools = useMemo(() => {
    const seen: string[] = [];
    for (const e of sseEvents) {
      if (e.event !== "tool_call") continue;
      const name = (e.data as Record<string, unknown>)?.tool as string | undefined;
      if (name && !seen.includes(name)) seen.push(name);
    }
    return seen;
  }, [sseEvents]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col">
        <AppNav />
        <div className="flex-1 flex items-center justify-center">
          <Loading label="Loading goal" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex flex-col">
        <AppNav />
        <div className="flex-1 flex items-center justify-center">
          <Empty
            title="That goal is not here"
            action={
              <Link to="/app" className="btn-ghost">
                Back to the dashboard
              </Link>
            }
          >
            {error
              ? "The goal could not be loaded. It may have been removed, or the backend is unreachable."
              : "Nothing is stored under this ID."}
          </Empty>
        </div>
      </div>
    );
  }

  const tasks = data.tasks ?? [];
  const done = tasks.filter((t) => toneOf(t.status) === "done").length;

  return (
    <div className="min-h-screen flex flex-col">
      <AppNav />

      {/* Run header — identity of this run, always in view. */}
      <div className="sticky top-14 z-30 border-b border-line bg-ink/92 backdrop-blur-md">
        <div className="px-5 h-12 flex items-center gap-4">
          <Link to="/app" className="micro hover:text-text transition-colors shrink-0">
            ← Dashboard
          </Link>
          <span className="w-px h-4 bg-line" />
          <p className="flex-1 min-w-0 truncate text-sm font-medium">{data.title}</p>
          {tasks.length > 0 && (
            <Micro>
              {done} / {tasks.length} tasks
            </Micro>
          )}
          <StatusBadge status={data.status} />
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row min-h-0">
        <Rail
          goalText={data.goal_text}
          tasks={tasks}
          tools={tools}
          live={isActive}
          watched={sseEvents.length > 0}
        />

        <div className="flex-1 min-w-0 flex flex-col">
          {tasks.length > 0 && (
            <div className="h-64 lg:h-80 border-b border-line">
              <TaskDAG tasks={tasks} />
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-5 space-y-px">
            {credRequest && (
              <div className="mb-4">
                <CredentialBanner req={credRequest} onDismiss={() => setCredRequest(null)} />
              </div>
            )}

            <div className="flex items-center justify-between pb-2">
              <Micro>Tasks</Micro>
              {tasks.length > 0 && <Micro>{tasks.length} total</Micro>}
            </div>

            {tasks.length === 0 && (
              <div className="panel">
                <Loading label="Orchestrator is planning the tasks" />
              </div>
            )}

            <div className="panel">
              {tasks.map((t) => (
                <TaskPanel key={t.id} task={t} />
              ))}
            </div>

            {data.output && (
              <div className="pt-6">
                <div className="pb-2">
                  <Micro>Output</Micro>
                </div>
                <OutputDisplay output={data.output} />
              </div>
            )}

            {data.error && (
              <div className="pt-6 space-y-px">
                <Notice>
                  <span className="font-mono text-xs leading-relaxed">{data.error}</span>
                </Notice>
                <ModelErrorBanner error={data.error} />
              </div>
            )}
          </div>
        </div>

        {/* The transcript — what the agents are doing, as they do it. */}
        <div className="w-full lg:w-96 shrink-0 flex flex-col border-t lg:border-t-0 lg:border-l border-line">
          <div className="border-b border-line px-4 py-2.5 flex items-center justify-between">
            <Micro>Live log</Micro>
            {isActive && (
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-violet animate-blip" />
                <Micro>Streaming</Micro>
              </span>
            )}
          </div>
          <div className="flex-1 overflow-hidden p-3">
            <LiveLog events={sseEvents} />
          </div>
        </div>
      </div>
    </div>
  );
}
