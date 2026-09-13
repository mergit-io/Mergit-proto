import { motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import useSWR, { mutate } from "swr";
import { api } from "../lib/api";
import { GoalCard } from "../components/GoalCard";
import { GoalInput } from "../components/GoalInput";

const fetcher = () => api.listGoals();

export function Dashboard() {
  const nav = useNavigate();
  const { data, isLoading } = useSWR("/api/goals", fetcher, { refreshInterval: 3000 });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (goal: string) => {
    setSubmitting(true);
    try {
      const res = await api.submitGoal(goal);
      await mutate("/api/goals");
      nav(`/goals/${res.goal_id}`);
    } catch (e) {
      console.error(e);
    } finally {
      setSubmitting(false);
    }
  };

  const goals = data?.goals ?? [];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold tracking-tight text-white">omni<span className="text-accent">Box</span></span>
          <span className="text-xs text-text-muted px-1.5 py-0.5 rounded bg-muted/30 border border-border">beta</span>
        </div>
        <p className="text-xs text-text-muted hidden sm:block">Delegate any goal to AI agents</p>
      </nav>

      {/* Hero */}
      <div className="flex flex-col items-center justify-center px-6 py-16 gap-6">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-2"
        >
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
            What do you want to <span className="text-accent">accomplish?</span>
          </h1>
          <p className="text-text-muted text-sm">
            Describe your goal — agents will decompose, plan, and execute it end-to-end.
          </p>
        </motion.div>
        <GoalInput onSubmit={handleSubmit} loading={submitting} />
      </div>

      {/* Goals list */}
      <div className="flex-1 px-6 pb-12 max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Recent Goals</h2>
          {!isLoading && <span className="text-xs text-text-muted">{goals.length} total</span>}
        </div>

        {isLoading && (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-14 rounded-xl bg-surface border border-border animate-pulse" />
            ))}
          </div>
        )}

        {!isLoading && goals.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-16 text-text-muted"
          >
            <p className="text-4xl mb-4">⚡</p>
            <p className="text-sm">No goals yet. Delegate your first one above.</p>
          </motion.div>
        )}

        <div className="space-y-2">
          {goals.map((g, i) => (
            <GoalCard key={g.goal_id} goal={g} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
}
