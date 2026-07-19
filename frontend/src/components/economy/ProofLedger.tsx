import { motion, AnimatePresence } from "framer-motion";
import type { Proof } from "../../lib/api";

function truncateHash(hash: string): string {
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function ProofLedger({ proofs }: { proofs: Proof[] }) {
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
            key={proof.task_id}
            layout
            initial={{ opacity: 0, x: -8, backgroundColor: "rgba(46,255,158,0.10)" }}
            animate={{ opacity: 1, x: 0, backgroundColor: "rgba(46,255,158,0)" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center justify-between px-5 py-3 gap-4"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-mono text-[11px] text-cyan shrink-0 w-20">
                #{proof.block_number.toLocaleString()}
              </span>
              <div className="min-w-0">
                <p className="font-mono text-xs text-white truncate">tx {truncateHash(proof.tx_hash)}</p>
                <p className="text-[11px] text-text-muted truncate">
                  <span className="capitalize">{proof.agent_role}</span> · sha256 {truncateHash(proof.result_hash)}
                </p>
              </div>
            </div>
            <div className="text-right shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-proof-green inline-block mr-2 align-middle" />
              <span className="text-[11px] text-text-muted align-middle">{timeAgo(proof.recorded_at)}</span>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
