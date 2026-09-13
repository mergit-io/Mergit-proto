import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { LeaderboardEntry } from "../../lib/api";

function truncate(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function Leaderboard({ entries }: { entries: LeaderboardEntry[] }) {
  const nav = useNavigate();

  if (entries.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-text-muted text-sm">
        No agents have earned reputation yet. Run a goal to mint the first proof.
      </div>
    );
  }

  return (
    <div className="card divide-y divide-white/6 overflow-hidden">
      <AnimatePresence initial={false}>
        {entries.map((entry) => (
          <motion.div
            key={entry.agent_name}
            layout
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            onClick={() => nav(`/app/economy/agents/${entry.agent_name}`)}
            className="flex items-center justify-between px-5 py-3.5 cursor-pointer hover:bg-white/[0.03] transition-colors"
          >
            <div className="flex items-center gap-4 min-w-0">
              <span className="w-6 text-sm font-mono text-text-muted shrink-0">
                #{entry.rank}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-white capitalize">{entry.agent_name}</p>
                <p className="text-xs font-mono text-text-muted">{truncate(entry.address)}</p>
              </div>
            </div>
            <div className="flex items-center gap-6 shrink-0">
              <span className="text-xs text-text-muted hidden sm:inline">
                {entry.tasks_completed} tasks
              </span>
              <span className="font-mono text-sm font-semibold text-cyan">
                {entry.reputation.toLocaleString()} REP
              </span>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
