import { motion, AnimatePresence } from "framer-motion";
import type { ProofRecord } from "../../lib/api";

function truncateHash(hash: string): string {
  return `${hash.slice(0, 10)}...${hash.slice(-6)}`;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export function ProofLedger({ proofs }: { proofs: ProofRecord[] }) {
  if (proofs.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-text-muted text-sm">
        No proofs minted yet. Every completed task mints one, live.
      </div>
    );
  }

  return (
    <div className="card divide-y divide-white/6 overflow-hidden">
      <AnimatePresence initial={false}>
        {proofs.map((proof) => (
          <motion.div
            key={proof.proof_id}
            layout
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center justify-between px-5 py-3 gap-4"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="w-1.5 h-1.5 rounded-full bg-proof-green shrink-0" />
              <div className="min-w-0">
                <p className="font-mono text-xs text-white truncate">{truncateHash(proof.tx_hash)}</p>
                <p className="text-[11px] text-text-muted capitalize">{proof.agent_name} · block {proof.block_number}</p>
              </div>
            </div>
            <div className="text-right shrink-0">
              <p className="font-mono text-sm text-proof-green">+{proof.reputation_delta} REP</p>
              <p className="text-[11px] text-text-muted">{timeAgo(proof.timestamp)}</p>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
