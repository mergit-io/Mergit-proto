import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import useSWR, { mutate } from "swr";
import { Bot, ChevronRight, Clock, Sparkles, Zap } from "lucide-react";
import { api } from "../lib/api";
import { GoalCard } from "../components/GoalCard";
import { GoalInput } from "../components/GoalInput";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import type { GoalSummary } from "../lib/api";

const fetcher = () => api.listGoals();

const STATUS_FILTERS = ["All", "RUNNING", "COMPLETED", "FAILED"] as const;
type Filter = (typeof STATUS_FILTERS)[number];

function StatsStrip({ goals }: { goals: GoalSummary[] }) {
  const running = goals.filter((g) => ["NEW", "PLANNING", "RUNNING"].includes(g.status)).length;
  const done = goals.filter((g) => g.status === "COMPLETED").length;
  const failed = goals.filter((g) => g.status === "FAILED").length;

  const stats = [
    { label: "Active", value: running, color: "text-accent", bg: "bg-accent/8 border-accent/15" },
    { label: "Completed", value: done, color: "text-success", bg: "bg-success/8 border-success/15" },
    { label: "Failed", value: failed, color: "text-danger", bg: "bg-danger/8 border-danger/15" },
    { label: "Total", value: goals.length, color: "text-white", bg: "bg-white/4 border-white/8" },
  ];

  return (
    <div className="grid grid-cols-4 gap-3 mb-8">
      {stats.map(({ label, value, color, bg }) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-xl border ${bg} px-4 py-3 text-center`}
        >
          <p className={`text-xl font-bold font-display ${color}`}>{value}</p>
          <p className="text-xs text-text-muted mt-0.5">{label}</p>
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
      className="flex flex-col items-center justify-center py-24 text-center"
    >
      <div className="relative mb-6">
        <div className="absolute inset-0 rounded-full bg-accent/20 blur-2xl scale-150" />
        <div className="relative w-16 h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center">
          <Bot className="w-8 h-8 text-accent" />
        </div>
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No goals yet</h3>
      <p className="text-sm text-text-muted max-w-xs leading-relaxed">
        Describe any goal above. Claude will decompose it into tasks and agents will execute it automatically.
      </p>
      <div className="mt-6 flex items-center gap-2 text-xs text-text-muted">
        <Sparkles className="w-3.5 h-3.5 text-accent" />
        <span>Try: "Research top LLM frameworks and post a summary to Slack"</span>
      </div>
    </motion.div>
  );
}

function SkeletonCard() {
  return (
    <div className="h-14 rounded-xl bg-surface border border-border animate-pulse" />
  );
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
  const filtered = filter === "All"
    ? allGoals
    : allGoals.filter((g) =>
        filter === "RUNNING"
          ? ["NEW", "PLANNING", "RUNNING"].includes(g.status)
          : g.status === filter
      );

  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
      <AppNav />

      {/* Main content */}
      <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">

        {/* Hero section */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="text-center mb-10"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/20 bg-accent/5 mb-5">
            <Zap className="w-3.5 h-3.5 text-accent" />
            <span className="text-xs font-medium text-accent">Multi-Agent Execution</span>
          </div>
          <h1 className="font-display font-bold text-white mb-3" style={{ fontSize: "clamp(1.8rem, 4vw, 2.8rem)" }}>
            What do you want to{" "}
            <span className="text-gradient">accomplish?</span>
          </h1>
          <p className="text-text-dim text-sm max-w-md mx-auto leading-relaxed">
            Describe any goal in natural language. Claude orchestrates specialized agents to plan and execute it end-to-end.
          </p>
        </motion.div>

        {/* Input */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="mb-3"
        >
          <GoalInput onSubmit={handleSubmit} loading={submitting} />
        </motion.div>

        {/* Submit error */}
        <AnimatePresence>
          {submitError && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mb-6 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 flex items-center gap-2"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-danger shrink-0" />
              <p className="text-sm text-red-400">{submitError}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Stats */}
        {!isLoading && allGoals.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
          >
            <StatsStrip goals={allGoals} />
          </motion.div>
        )}

        {/* Goals list */}
        <div>
          {/* Header + filter */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-text-muted" />
              <h2 className="text-xs font-semibold text-text-muted uppercase tracking-widest">Recent Goals</h2>
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-white/8 bg-black/30 backdrop-blur-sm p-0.5">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 ${
                    filter === f
                      ? "bg-accent text-white"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  {f === "All" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Loading skeleton */}
          {isLoading && (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && filtered.length === 0 && allGoals.length === 0 && <EmptyState />}
          {!isLoading && filtered.length === 0 && allGoals.length > 0 && (
            <p className="text-center text-sm text-text-muted py-12">No goals match this filter.</p>
          )}

          {/* Goal cards */}
          <AnimatePresence mode="popLayout">
            <div className="space-y-2">
              {filtered.map((g, i) => (
                <GoalCard key={g.goal_id} goal={g} index={i} />
              ))}
            </div>
          </AnimatePresence>

          {/* Load more hint */}
          {!isLoading && filtered.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
              className="mt-4 flex items-center justify-center gap-1.5 text-xs text-text-muted"
            >
              <span>Showing {filtered.length} goal{filtered.length !== 1 ? "s" : ""}</span>
              {data && data.total > allGoals.length && (
                <>
                  <ChevronRight className="w-3 h-3" />
                  <span>{data.total - allGoals.length} more not loaded</span>
                </>
              )}
            </motion.div>
          )}
        </div>
      </main>
      </div>
    </div>
  );
}
