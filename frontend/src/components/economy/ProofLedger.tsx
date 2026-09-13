import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../../lib/api";
import type { ChainStatusInfo, Proof, ProofVerification } from "../../lib/api";

function truncateHash(hash: string): string {
  if (!hash) return "—";
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function VerifyResult({ result }: { result: ProofVerification }) {
  if (result.verified === true) {
    return (
      <div className="mt-2 rounded-lg border border-proof-green/25 bg-proof-green/5 px-3 py-2">
        <p className="text-[11px] text-proof-green font-medium">
          ✓ Verified — the stored output hashes to exactly what is on chain.
        </p>
        <p className="font-mono text-[10px] text-text-muted mt-1 break-all">
          sha256 {result.computed_hash}
        </p>
      </div>
    );
  }

  if (result.verified === false) {
    return (
      <div className="mt-2 rounded-lg border border-red-400/30 bg-red-400/5 px-3 py-2">
        <p className="text-[11px] text-red-400 font-medium">
          ✗ Mismatch — the stored output was altered after the proof was recorded.
        </p>
        <p className="font-mono text-[10px] text-text-muted mt-1 break-all">
          computed {truncateHash(result.computed_hash)} · on-chain{" "}
          {truncateHash(result.onchain_hash ?? "")}
        </p>
      </div>
    );
  }

  const reason =
    result.reason === "not_recorded"
      ? "Not yet recorded on chain."
      : result.reason === "chain_unavailable"
        ? "Chain unavailable — cannot verify right now."
        : "Nothing on chain to compare against.";

  return (
    <div className="mt-2 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2">
      <p className="text-[11px] text-text-muted">{reason}</p>
      <p className="font-mono text-[10px] text-text-muted mt-1 break-all">
        would prove sha256 {truncateHash(result.computed_hash)}
      </p>
    </div>
  );
}

export function ProofLedger({
  proofs,
  chain,
}: {
  proofs: Proof[];
  chain?: ChainStatusInfo | null;
}) {
  const [verifications, setVerifications] = useState<Record<string, ProofVerification>>({});
  const [verifying, setVerifying] = useState<string | null>(null);

  async function verify(taskId: string) {
    setVerifying(taskId);
    try {
      const result = await api.verifyProof(taskId);
      setVerifications((prev) => ({ ...prev, [taskId]: result }));
    } catch {
      /* leave unverified — the row simply shows no result */
    } finally {
      setVerifying(null);
    }
  }

  if (proofs.length === 0) {
    return (
      <div className="card px-6 py-10 text-center text-text-muted text-sm">
        No proofs minted yet. Every completed task mints one, live.
      </div>
    );
  }

  return (
    <div className="card divide-y divide-white/6 overflow-hidden">
      {chain && (
        <div className="flex items-center justify-between px-5 py-2.5 bg-white/[0.02]">
          <span className="text-[11px] text-text-muted">
            {chain.name} · chainId <span className="font-mono text-cyan">{chain.chainId}</span>
          </span>
          {chain.outbox?.pending ? (
            <span className="text-[11px] text-amber-400">
              {chain.outbox.pending} awaiting chain
            </span>
          ) : null}
        </div>
      )}

      <AnimatePresence initial={false}>
        {proofs.map((proof) => {
          const result = verifications[proof.task_id];
          const explorerUrl = chain?.explorer ? `${chain.explorer}/tx/${proof.tx_hash}` : null;

          return (
            <motion.div
              key={proof.task_id}
              layout
              initial={{ opacity: 0, x: -8, backgroundColor: "rgba(46,255,158,0.10)" }}
              animate={{ opacity: 1, x: 0, backgroundColor: "rgba(46,255,158,0)" }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="px-5 py-3"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="font-mono text-[11px] text-cyan shrink-0 w-20">
                    #{proof.block_number.toLocaleString()}
                  </span>
                  <div className="min-w-0">
                    {explorerUrl ? (
                      <a
                        href={explorerUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-xs text-white truncate hover:text-cyan transition-colors"
                      >
                        tx {truncateHash(proof.tx_hash)} ↗
                      </a>
                    ) : (
                      <p className="font-mono text-xs text-white truncate">
                        tx {truncateHash(proof.tx_hash)}
                      </p>
                    )}
                    <p className="text-[11px] text-text-muted truncate">
                      <span className="capitalize">{proof.agent_role}</span> · sha256{" "}
                      {truncateHash(proof.result_hash)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={() => verify(proof.task_id)}
                    disabled={verifying === proof.task_id}
                    className="text-[11px] px-2.5 py-1 rounded-md border border-white/12
                               text-text-muted hover:text-white hover:border-white/25
                               disabled:opacity-50 transition-colors"
                  >
                    {verifying === proof.task_id ? "Verifying…" : "Verify"}
                  </button>
                  <span className="text-right">
                    <span className="w-1.5 h-1.5 rounded-full bg-proof-green inline-block mr-2 align-middle" />
                    <span className="text-[11px] text-text-muted align-middle">
                      {timeAgo(proof.recorded_at)}
                    </span>
                  </span>
                </div>
              </div>

              {result && <VerifyResult result={result} />}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
