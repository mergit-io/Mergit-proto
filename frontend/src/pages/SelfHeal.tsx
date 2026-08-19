import useSWR from "swr";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { api } from "../lib/api";
import type { HealAttempt } from "../lib/api";

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const STATUS_META: Record<string, { label: string; className: string }> = {
  filed: { label: "Issue filed", className: "text-cyan border-cyan/25 bg-cyan/8" },
  simulated: {
    label: "Simulated",
    className: "text-amber-400 border-amber-400/25 bg-amber-400/8",
  },
};

const OUTCOME_META: Record<string, { label: string; className: string }> = {
  fixed: { label: "Fixed", className: "text-proof-deep border-proof/25 bg-proof/8" },
  failed: { label: "Fix failed", className: "text-red-400 border-red-400/25 bg-red-400/8" },
  abandoned: { label: "Abandoned", className: "text-ink-muted border-ink/[0.09] bg-white" },
};

function Chip({ label, className }: { label: string; className: string }) {
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${className}`}>
      {label}
    </span>
  );
}

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="card px-4 py-3">
      <p className="font-mono text-xl text-ink leading-none">{value}</p>
      <p className="text-[11px] text-ink-muted mt-1.5">{label}</p>
    </div>
  );
}

function AttemptRow({ attempt }: { attempt: HealAttempt }) {
  const nav = useNavigate();
  const status = STATUS_META[attempt.status];
  const outcome = attempt.outcome ? OUTCOME_META[attempt.outcome] : null;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="px-5 py-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="text-xs font-medium text-ink capitalize">{attempt.agent_name}</span>
            {status && <Chip label={status.label} className={status.className} />}
            {outcome && <Chip label={outcome.label} className={outcome.className} />}
            {attempt.recurrence_count > 1 && (
              <Chip
                label={`seen ${attempt.recurrence_count}×`}
                className="text-violet-300 border-violet-400/25 bg-violet-400/8"
              />
            )}
          </div>

          <p className="font-mono text-[11px] text-ink-dim break-all">{attempt.error_summary}</p>

          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="font-mono text-[10px] text-ink-muted">
              {attempt.fingerprint.slice(0, 12)}
            </span>
            {attempt.issue_url && (
              <a
                href={attempt.issue_url}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-cyan hover:underline"
              >
                issue #{attempt.issue_number} ↗
              </a>
            )}
            {attempt.fix_goal_id && (
              <button
                onClick={() => nav(`/app/goals/${attempt.fix_goal_id}`)}
                className="text-[11px] text-accent-2 hover:underline"
              >
                view fix goal →
              </button>
            )}
          </div>
        </div>

        <span className="text-[11px] text-ink-muted shrink-0">{timeAgo(attempt.created_at)}</span>
      </div>
    </motion.div>
  );
}

export function SelfHeal() {
  const { data: attempts } = useSWR("/api/heal/attempts", () => api.getHealAttempts(), {
    refreshInterval: 5000,
  });
  const { data: stats } = useSWR("/api/heal/stats", () => api.getHealStats(), {
    refreshInterval: 5000,
  });

  return (
    <div className="relative min-h-screen" style={{ background: "#FFFDFB" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />

        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mb-8"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/25 bg-accent/8 mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-proof animate-pulse-ring" />
              <span className="text-xs font-medium text-accent-2">Autonomous repair</span>
            </div>

            <h1
              className="font-display font-bold text-ink mb-3"
              style={{ fontSize: "clamp(1.8rem, 4vw, 2.6rem)" }}
            >
              Self-<span className="text-accent">Heal</span>
            </h1>
            <p className="text-ink-dim text-sm max-w-xl leading-relaxed">
              When a run fails from a bug in Mergit's own code — not a rate limit or a bad key —
              the system fingerprints the error, files an issue, and spawns an agent pipeline to
              fix itself. Repeat failures deduplicate instead of filing again.
            </p>
          </motion.div>

          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
              <Stat value={stats.total} label="Distinct bugs" />
              <Stat value={stats.recurrences} label="Total occurrences" />
              <Stat value={stats.fixed} label="Fixed" />
              <Stat value={stats.by_status?.filed ?? 0} label="Issues filed" />
            </div>
          )}

          {!attempts || attempts.length === 0 ? (
            <div className="card px-6 py-10 text-center text-ink-muted text-sm">
              No bugs detected yet. Developer-side failures appear here automatically.
            </div>
          ) : (
            <div className="card divide-y divide-ink/[0.08] overflow-hidden">
              {attempts.map((attempt) => (
                <AttemptRow key={attempt.id} attempt={attempt} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
