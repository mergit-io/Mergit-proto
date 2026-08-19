import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { RepEntry } from "../../lib/api";

export function badgeStyle(badge: string): string {
  switch (badge) {
    case "Gold":
      return "bg-[#f5c54215] text-[#f5c542] border-[#f5c54235]";
    case "Silver":
      return "bg-[#c8d0dc15] text-[#c8d0dc] border-[#c8d0dc35]";
    default:
      return "bg-[#c67b4615] text-[#d89b6e] border-[#c67b4635]";
  }
}

export function Leaderboard({ entries }: { entries: RepEntry[] }) {
  const nav = useNavigate();

  if (entries.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-ink-muted text-sm">
        No agents have earned reputation yet. Run a goal to mint the first proof.
      </div>
    );
  }

  return (
    <div className="card divide-y divide-ink/[0.08] overflow-hidden">
      <AnimatePresence initial={false}>
        {entries.map((entry) => (
          <motion.div
            key={entry.role}
            layout
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            onClick={() => nav(`/app/economy/agents/${entry.role}`)}
            className="px-5 py-3.5 cursor-pointer hover:bg-white/[0.03] transition-colors"
          >
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-4 min-w-0">
                <span className="w-6 text-sm font-mono text-ink-muted shrink-0">
                  #{entry.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink capitalize">{entry.role}</p>
                  <p className="text-[11px] font-mono text-ink-muted">
                    {(entry.success_rate * 100).toFixed(0)}% success · {(entry.speed * 100).toFixed(0)}% speed
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4 shrink-0">
                <span
                  className={`text-[10px] font-semibold uppercase tracking-widest px-2 py-1 rounded-full border ${badgeStyle(entry.badge)}`}
                >
                  {entry.badge}
                </span>
                <span className="font-mono text-sm font-semibold text-cyan w-14 text-right">
                  {entry.composite}
                </span>
              </div>
            </div>
            {/* score bar */}
            <div className="mt-2.5 h-1 rounded-full bg-white overflow-hidden">
              <motion.div
                layout
                className="h-full rounded-full bg-gradient-to-r from-accent to-cyan"
                initial={false}
                animate={{ width: `${(entry.composite / 1000) * 100}%` }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
