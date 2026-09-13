import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { GoalSummary } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

interface Props {
  goal: GoalSummary;
  index: number;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export function GoalCard({ goal, index }: Props) {
  const nav = useNavigate();
  const isActive = ["NEW", "PLANNING", "RUNNING"].includes(goal.status);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      onClick={() => nav(`/app/goals/${goal.goal_id}`)}
      className="group relative flex items-center justify-between rounded-xl border border-white/6 bg-white/[0.02] px-4 py-3.5 cursor-pointer hover:border-accent/25 hover:bg-white/[0.04] transition-all duration-200 overflow-hidden"
    >
      {/* Active glow strip */}
      {isActive && (
        <div className="absolute left-0 top-0 bottom-0 w-0.5 rounded-l-xl bg-accent" />
      )}

      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-200 group-hover:text-white transition-colors">
            {goal.title}
          </p>
          <p className="text-xs text-text-muted mt-0.5">{timeAgo(goal.created_at)}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0 ml-4">
        <StatusBadge status={goal.status} size="sm" />
        <ChevronRight className="w-3.5 h-3.5 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </motion.div>
  );
}
