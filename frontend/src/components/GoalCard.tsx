import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { GoalSummary } from "../lib/api";

interface Props {
  goal: GoalSummary;
  index: number;
}

const ACTIVE = ["NEW", "PLANNING", "RUNNING"];

/**
 * Status pill is local rather than the shared StatusBadge: that component still renders on the
 * dark run page and its dark-surface colours would wash out here. It migrates with those pages.
 */
function pill(status: string): { label: string; className: string; dot: string } {
  if (ACTIVE.includes(status)) {
    return { label: status === "RUNNING" ? "running" : status.toLowerCase(), className: "bg-[#F1EBFF] text-[#5B4BA8]", dot: "bg-accent" };
  }
  if (status === "COMPLETED" || status === "DONE") {
    return { label: "done", className: "bg-[#E9F9F2] text-proof-deep", dot: "bg-proof" };
  }
  if (status === "FAILED") {
    return { label: "failed", className: "bg-[#FFF1EF] text-[#C2453B]", dot: "bg-[#E86A5E]" };
  }
  if (status === "WAITING_WEBHOOK") {
    return { label: "waiting", className: "bg-[#FFF6E8] text-[#A16207]", dot: "bg-[#EAB308]" };
  }
  return { label: status.toLowerCase(), className: "bg-ink/[0.05] text-ink-muted", dot: "bg-ink-dim" };
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
  const p = pill(goal.status);

  return (
    <motion.button
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      onClick={() => nav(`/app/goals/${goal.goal_id}`)}
      className="group flex w-full items-center gap-4 rounded-[20px] border border-ink/[0.09] bg-white px-5 py-4 text-left transition-colors hover:border-accent/30 hover:bg-paper-2"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] font-semibold text-ink">{goal.title}</p>
        <p className="mt-1 font-mono text-[11px] text-ink-dim">{timeAgo(goal.created_at)}</p>
      </div>
      <span
        className={`inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${p.className}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
        {p.label}
      </span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-dim opacity-0 transition-opacity group-hover:opacity-100" />
    </motion.button>
  );
}
