import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import useSWR, { mutate } from "swr";
import { Bot, Clock, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { GoalCard } from "../components/GoalCard";
import { GoalInput } from "../components/GoalInput";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import type { GoalSummary } from "../lib/api";

const fetcher = () => api.listGoals();

const STATUS_FILTERS = ["All", "RUNNING", "COMPLETED", "FAILED"] as const;
type Filter = (typeof STATUS_FILTERS)[number];

const SUGGESTIONS = [
  "Review the open pull requests on a repo",
  "Research and write a comparison report",
  "Ship a small CLI as a new GitHub repo",
];

const ACTIVE = ["NEW", "PLANNING", "RUNNING"];

function StatsStrip({ goals }: { goals: GoalSummary[] }) {
  const stats = [
    { label: "active", value: goals.filter((g) => ACTIVE.includes(g.status)).length, tone: "border-accent/20 text-accent", dot: "bg-accent" },
    { label: "completed", value: goals.filter((g) => g.status === "COMPLETED").length, tone: "border-proof/25 text-proof-deep", dot: "bg-proof" },
    { label: "failed", value: goals.filter((g) => g.status === "FAILED").length, tone: "border-[#E86A5E]/25 text-[#C2453B]", dot: "bg-[#E86A5E]" },
    { label: "total", value: goals.length, tone: "border-ink/10 text-ink", dot: "bg-ink-dim" },
  ];

  return (
    <div className="mb-9 grid grid-cols-2 gap-3.5 sm:grid-cols-4">
      {stats.map(({ label, value, tone, dot }) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-[20px] border bg-white px-5 py-4 ${tone}`}
        >
          <div className="mb-2.5 flex items-center justify-between">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">{label}</p>
            <span className={`h-2 w-2 rounded-full ${dot}`} />
          </div>
          <p className="font-sora text-3xl font-extrabold">{value}</p>
        </motion.div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center rounded-[24px] border border-dashed border-ink/15 bg-white/60 py-20 text-center"
    >
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#F1EBFF]">
        <Bot className="h-7 w-7 text-accent" />
      </div>
      <h3 className="font-sora text-lg font-bold text-ink">No goals yet</h3>
      <p className="mt-2 max-w-xs text-sm leading-relaxed text-ink-muted">
        Describe a goal above. It gets planned into tasks, and the agents run it end to end.
      </p>
      <div className="mt-5 flex items-center gap-2 text-xs text-ink-dim">
        <Sparkles className="h-3.5 w-3.5 text-accent" />
        <span>Try: “Fix the bug in issue #1 and open a pull request”</span>
      </div>
    </motion.div>
  );
}

function SkeletonCard() {
  return <div className="h-[68px] animate-pulse rounded-[20px] border border-ink/[0.07] bg-white/70" />;
}

export function Dashboard() {
  const nav = useNavigate();
  const { data, isLoading } = useSWR("/api/goals", fetcher, { refreshInterval: 3000 });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("All");

  const handleSubmit = async (goal: string) => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await api.submitGoal(goal);
      await mutate("/api/goals");
      nav(`/app/goals/${res.goal_id}`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to submit goal");
    } finally {
      setSubmitting(false);
    }
  };

  const allGoals = data?.goals ?? [];
  const filtered =
    filter === "All"
      ? allGoals
      : allGoals.filter((g) => (filter === "RUNNING" ? ACTIVE.includes(g.status) : g.status === filter));

  return (
    <div className="relative min-h-screen bg-paper font-manrope text-ink">
      <AppBackground />
      <div className="relative z-10 flex min-h-screen flex-col">
        <AppNav />

        <main className="mx-auto w-full max-w-[1160px] flex-1 px-5 py-12 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mx-auto mb-7 max-w-[820px] text-center"
          >
            <h1 className="mb-3 font-sora text-[clamp(1.9rem,4vw,2.9rem)] font-extrabold leading-[1.06] tracking-[-0.035em]">
              What should Mergit do?
            </h1>
            <p className="text-[15px] leading-relaxed text-ink-muted sm:text-base">
              One sentence. It plans the tasks, picks the agents, calls the tools and runs it end to end.
            </p>
          </motion.div>

          <div className="mx-auto mb-4 max-w-[820px]">
            <GoalInput onSubmit={handleSubmit} loading={submitting} />
          </div>

          <AnimatePresence>
            {submitError && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mx-auto mb-6 flex max-w-[820px] items-center gap-2.5 rounded-2xl border border-[#E86A5E]/30 bg-[#FFF1EF] px-4 py-3"
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#E86A5E]" />
                <p className="text-sm text-[#C2453B]">{submitError}</p>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mx-auto mb-11 flex max-w-[820px] flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => handleSubmit(s)}
                disabled={submitting}
                className="rounded-full border border-ink/10 bg-white/85 px-4 py-2 text-xs text-ink-muted transition-colors hover:border-accent/30 hover:text-ink disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>

          {!isLoading && allGoals.length > 0 && <StatsStrip goals={allGoals} />}

          <div>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Clock className="h-3.5 w-3.5 text-ink-dim" />
                <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Recent goals</h2>
              </div>
              <div className="flex items-center gap-1 rounded-[13px] bg-ink/[0.05] p-1">
                {STATUS_FILTERS.map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`rounded-[9px] px-3 py-1.5 text-xs font-medium transition-colors ${
                      filter === f ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    {f === "All" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>
            </div>

            {isLoading && (
              <div className="space-y-2.5">
                {[...Array(4)].map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {!isLoading && filtered.length === 0 && allGoals.length === 0 && <EmptyState />}
            {!isLoading && filtered.length === 0 && allGoals.length > 0 && (
              <p className="py-12 text-center text-sm text-ink-dim">No goals match this filter.</p>
            )}

            <div className="space-y-2.5">
              {filtered.map((g, i) => (
                <GoalCard key={g.goal_id} goal={g} index={i} />
              ))}
            </div>

            {!isLoading && filtered.length > 0 && (
              <p className="mt-5 text-center font-mono text-[11px] text-ink-dim">
                Showing {filtered.length} goal{filtered.length !== 1 ? "s" : ""}
                {data && data.total > allGoals.length ? ` · ${data.total - allGoals.length} more not loaded` : ""}
              </p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
