import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { AgentPassport } from "../../lib/api";

function truncate(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function PassportCard({ passport, index = 0 }: { passport: AgentPassport; index?: number }) {
  const nav = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      onClick={() => nav(`/app/economy/agents/${passport.agent_name}`)}
      className="card p-5 cursor-pointer hover:border-accent/25 transition-colors"
    >
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-white capitalize">{passport.agent_name}</p>
        <span className="text-[10px] font-semibold uppercase tracking-widest px-2 py-1 rounded-full bg-accent/10 text-accent border border-accent/20">
          Level {passport.level}
        </span>
      </div>

      <p className="text-xs font-mono text-text-muted mb-4">{truncate(passport.address)}</p>

      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-2xl font-bold text-cyan">{passport.reputation.toLocaleString()}</p>
          <p className="text-[11px] text-text-muted uppercase tracking-wide">Reputation</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm text-proof-green">{passport.tasks_completed} done</p>
          {passport.tasks_failed > 0 && (
            <p className="font-mono text-xs text-danger">{passport.tasks_failed} failed</p>
          )}
        </div>
      </div>
    </motion.div>
  );
}
