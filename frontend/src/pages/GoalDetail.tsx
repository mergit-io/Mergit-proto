import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, RefreshCw, AlertCircle, Key, Eye, EyeOff, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { LiveLog } from "../components/LiveLog";
import { OutputDisplay } from "../components/OutputDisplay";
import { StatusBadge } from "../components/StatusBadge";
import { TaskDAG } from "../components/TaskDAG";
import { RunPipeline } from "../components/RunPipeline";
import { TaskPanel } from "../components/TaskPanel";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { ModelErrorBanner } from "../components/ModelErrorBanner";
import { api } from "../lib/api";
import { useSSE } from "../lib/sse";

const ACTIVE_STATUSES = new Set(["NEW", "PLANNING", "RUNNING"]);

type StageView = "flow" | "graph";

interface CredentialRequest {
  task_id: string;
  credential: string;
  provider: string;
  message: string;
}

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
      setErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="mx-5 mt-4 rounded-2xl border border-[#EAB308]/30 bg-[#FFF6E8] p-4 sm:mx-8"
    >
      <div className="flex items-start gap-3">
        <Key className="mt-0.5 h-4 w-4 shrink-0 text-[#A16207]" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#A16207]">Credential required</p>
          <p className="mt-0.5 text-xs text-[#A16207]/80">{req.message}</p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex flex-1 items-center gap-2 rounded-xl border border-ink/12 bg-white px-3 py-2">
              <input
                type={show ? "text" : "password"}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") save();
                }}
                placeholder={`Paste ${req.credential}…`}
                autoFocus
                className="flex-1 bg-transparent font-mono text-xs text-ink outline-none placeholder:text-ink-dim"
              />
              <button
                onClick={() => setShow((v) => !v)}
                className="text-ink-dim transition-colors hover:text-ink"
                aria-label={show ? "Hide value" : "Show value"}
              >
                {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
            <button
              onClick={save}
              disabled={saving || !value.trim()}
              className="rounded-xl bg-[#A16207] px-4 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? "Saving…" : "Save & resume"}
            </button>
          </div>
          {err && <p className="mt-1.5 text-xs text-[#C2453B]">{err}</p>}
        </div>
        <button onClick={onDismiss} className="shrink-0 text-ink-dim transition-colors hover:text-ink" aria-label="Dismiss">
          <X className="h-4 w-4" />
        </button>
      </div>
    </motion.div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen bg-paper font-manrope text-ink">
      <AppBackground />
      <div className="relative z-10 flex min-h-screen flex-col">
        <AppNav />
        {children}
      </div>
    </div>
  );
}

function fetcher(id: string) {
  return api.getGoal(id);
}

export function GoalDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [view, setView] = useState<StageView>("flow");
  const { data, isLoading, error } = useSWR(
    id ? `/api/goals/${id}` : null,
    () => fetcher(id!),
    { refreshInterval: (d) => (d && ACTIVE_STATUSES.has(d.status) ? 2000 : 0) }
  );

  const isActive = data ? ACTIVE_STATUSES.has(data.status) : false;
  const sseEvents = useSSE(id, isActive);

  // Derived from the stream rather than copied into state by an effect: the banner is a pure
  // function of "latest credential_request, unless the user dismissed that one".
  const [dismissedTask, setDismissedTask] = useState<string | null>(null);
  const latestCred = [...sseEvents]
    .reverse()
    .find((e) => e.event === "credential_request")?.data as CredentialRequest | undefined;
  const credRequest = latestCred && latestCred.task_id !== dismissedTask ? latestCred : null;

  if (isLoading) {
    return (
      <Shell>
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2.5 text-ink-muted">
            <RefreshCw className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading goal…</span>
          </div>
        </div>
      </Shell>
    );
  }

  if (error || !data) {
    return (
      <Shell>
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-center">
            <AlertCircle className="h-8 w-8 text-[#E86A5E]" />
            <p className="text-sm text-ink-muted">{error ? `Error: ${error.message}` : "Goal not found."}</p>
            <button onClick={() => nav("/app")} className="text-xs font-medium text-accent hover:underline">
              ← Back to dashboard
            </button>
          </div>
        </div>
      </Shell>
    );
  }

  const tasks = data.tasks ?? [];

  const viewSwitch = (
    <div className="flex items-center gap-1 rounded-[11px] bg-white p-1 shadow-sm">
      {(["flow", "graph"] as const).map((v) => (
        <button
          key={v}
          onClick={() => setView(v)}
          className={`rounded-lg px-3 py-1.5 font-mono text-[11px] transition-colors ${
            view === v ? "bg-ink/[0.06] text-ink" : "text-ink-dim hover:text-ink"
          }`}
        >
          {v}
        </button>
      ))}
    </div>
  );

  return (
    <Shell>
      {/* goal header */}
      <div className="border-b border-ink/[0.07] bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-5 py-4 sm:px-8">
          <button
            onClick={() => nav("/app")}
            className="flex shrink-0 items-center gap-1.5 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Dashboard
          </button>
          <span className="hidden h-4 w-px bg-ink/10 sm:block" />
          <p className="min-w-0 flex-1 truncate font-sora text-[15px] font-bold text-ink">{data.title}</p>
          <span className="shrink-0 rounded-lg bg-ink/[0.05] px-2.5 py-1 font-mono text-[11px] text-ink-muted">
            {tasks.length} task{tasks.length !== 1 ? "s" : ""}
          </span>
          <StatusBadge status={data.status} />
        </div>
      </div>

      <AnimatePresence>
        {credRequest && <CredentialBanner req={credRequest} onDismiss={() => setDismissedTask(credRequest.task_id)} />}
      </AnimatePresence>

      {/* run overview */}
      {tasks.length > 0 && (
        <div className="border-b border-ink/[0.07] bg-paper-2/60">
          {view === "flow" ? (
            <RunPipeline tasks={tasks} goalStatus={data.status} action={viewSwitch} />
          ) : (
            <div className="mx-auto w-full max-w-[1400px] px-5 py-6 sm:px-8">
              <div className="mb-5 flex items-center justify-between gap-3">
                <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Run</p>
                {viewSwitch}
              </div>
              <div className="h-[300px] lg:h-[400px]">
                <TaskDAG tasks={tasks} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* body */}
      <div className="mx-auto grid w-full max-w-[1400px] flex-1 grid-cols-1 gap-0 lg:grid-cols-[1fr_380px]">
        <div className="border-ink/[0.07] px-5 py-7 sm:px-8 lg:border-r">
          <div className="mb-4 flex items-center gap-2.5">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Tasks</p>
            {tasks.length > 0 && (
              <span className="rounded-md bg-ink/[0.05] px-2 py-0.5 font-mono text-[11px] text-ink-muted">
                {tasks.length}
              </span>
            )}
          </div>

          {tasks.length === 0 && (
            <div className="flex items-center gap-2.5 py-4 text-sm text-ink-muted">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Orchestrator is planning tasks…</span>
            </div>
          )}

          <div className="space-y-2.5">
            {tasks.map((t) => (
              <TaskPanel key={t.id} task={t} />
            ))}
          </div>

          {data.output && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-7">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Output</p>
              <OutputDisplay output={data.output} />
            </motion.div>
          )}

          {data.error && (
            <>
              <div className="mt-5 rounded-2xl border border-[#E86A5E]/25 bg-[#FFF1EF] p-4">
                <div className="mb-1.5 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-[#C2453B]" />
                  <p className="text-sm font-semibold text-[#C2453B]">Goal failed</p>
                </div>
                <p className="font-mono text-[11px] leading-relaxed text-[#C2453B]">{data.error}</p>
              </div>
              <ModelErrorBanner error={data.error} />
            </>
          )}
        </div>

        {/* live log */}
        <div className="flex flex-col border-t border-ink/[0.07] bg-paper-2/70 lg:border-t-0">
          <div className="flex items-center justify-between px-5 py-4 sm:px-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Live log</p>
            {isActive && (
              <span className="flex items-center gap-1.5 font-mono text-[11px] text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                streaming
              </span>
            )}
          </div>
          <div className="min-h-[240px] flex-1 overflow-hidden px-5 pb-5 sm:px-6">
            <LiveLog events={sseEvents} />
          </div>
        </div>
      </div>
    </Shell>
  );
}
