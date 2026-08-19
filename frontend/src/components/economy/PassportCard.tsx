import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { Passport } from "../../lib/api";

function truncate(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function PassportCard({ passport, index = 0 }: { passport: Passport; index?: number }) {
  const nav = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      onClick={() => nav(`/app/economy/agents/${passport.role}`)}
      className="relative rounded-2xl p-[1px] cursor-pointer bg-gradient-to-br from-accent/40 via-cyan/25 to-transparent hover:from-accent/70 hover:via-cyan/40 transition-colors"
    >
      <div className="rounded-2xl bg-white backdrop-blur-sm p-5 h-full">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-ink capitalize">{passport.role}</p>
            <p className="text-[11px] font-mono text-ink-muted">AgentPassport #{passport.token_id}</p>
          </div>
          {passport.soulbound && (
            <span className="text-[9px] font-semibold uppercase tracking-widest px-2 py-1 rounded-full bg-accent/10 text-accent-2 border border-accent/25">
              Soulbound
            </span>
          )}
        </div>

        <dl className="space-y-1.5 mb-4">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-[11px] text-ink-muted">DID</dt>
            <dd className="text-[11px] font-mono text-ink-dim truncate max-w-[70%]">{passport.did}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-[11px] text-ink-muted">Owner</dt>
            <dd className="text-[11px] font-mono text-ink-dim">{truncate(passport.owner_address)}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-[11px] text-ink-muted">Mint block</dt>
            <dd className="text-[11px] font-mono text-cyan">#{passport.mint_block.toLocaleString()}</dd>
          </div>
        </dl>

        <div className="flex flex-wrap gap-1.5">
          {passport.capabilities.slice(0, 6).map((cap) => (
            <span
              key={cap}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white text-ink-dim border border-ink/[0.09]"
            >
              {cap}
            </span>
          ))}
          {passport.capabilities.length === 0 && (
            <span className="text-[10px] text-ink-muted">no tools</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}
