import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { GoalSummary } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

interface Props {
  goal: GoalSummary;
  index: number;
}

export function GoalCard({ goal, index }: Props) {
  const nav = useNavigate();
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.25 }}
      onClick={() => nav(`/goals/${goal.goal_id}`)}
      className="group flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3.5 cursor-pointer hover:border-muted hover:bg-white/[0.02] transition-all duration-150"
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-100 group-hover:text-white transition-colors">
            {goal.title}
          </p>
          <p className="text-xs text-text-muted mt-0.5">
            {new Date(goal.created_at * 1000).toLocaleString()}
          </p>
        </div>
      </div>
      <StatusBadge status={goal.status} size="sm" />
    </motion.div>
  );
}
