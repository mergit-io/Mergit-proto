import { Fragment, useState } from "react";
import { api } from "../../lib/api";
import type { ChainStatusInfo, Proof, ProofVerification } from "../../lib/api";
import { Empty, Hash, Micro, Notice, settlementLabel } from "../ui";

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
      <Notice tone="done">
        Verified — the stored output hashes to exactly what is on chain.{" "}
        <span className="font-mono text-xs">sha256 {result.computed_hash}</span>
      </Notice>
    );
  }

  if (result.verified === false) {
    return (
      <Notice tone="fail">
        Mismatch — the stored output was altered after the proof was recorded.{" "}
        <span className="font-mono text-xs">
          computed <Hash value={result.computed_hash} /> · on-chain{" "}
          <Hash value={result.onchain_hash} />
        </span>
      </Notice>
    );
  }

  const reason =
    result.reason === "not_recorded"
      ? "Not yet recorded on chain."
      : result.reason === "chain_unavailable"
        ? "Chain unavailable — cannot verify right now."
        : "Nothing on chain to compare against.";

  return (
    <Notice tone="wait">
      {reason}{" "}
      <span className="font-mono text-xs">would prove sha256 {result.computed_hash}</span>
    </Notice>
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
    return <Empty title="No proofs minted yet">Every completed task mints one, live.</Empty>;
  }

  return (
    <div>
      {chain && (
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-line-soft">
          {/* With the chain off both halves are null, and this rendered a bare "· chain id". */}
          <Micro>
            {chain.chainId ? `${chain.name} · chain id ${chain.chainId}` : "Chain disabled"}
          </Micro>
          {chain.outbox?.pending ? (
            <span className="font-mono text-micro uppercase text-amber">
              {chain.outbox.pending} awaiting chain
            </span>
          ) : null}
        </div>
      )}

      <table className="dtable">
        <thead>
          <tr>
            <th>Block</th>
            <th>Tx</th>
            <th>Agent</th>
            <th>Recorded</th>
            <th className="text-right">Verify</th>
          </tr>
        </thead>
        <tbody>
          {proofs.map((proof) => {
            const result = verifications[proof.task_id];
            // Only a hash the chain actually issued gets a link. The ledger also carries a
            // locally minted hash so a proof can appear the instant a task finishes, and
            // linking that produced an explorer page for a transaction that never existed.
            const explorerUrl =
              chain?.explorer && proof.tx_hash ? `${chain.explorer}/tx/${proof.tx_hash}` : null;

            return (
              <Fragment key={proof.task_id}>
                <tr>
                  <td className="font-mono text-xs tabular text-dim">
                    {proof.block_number !== null ? `#${proof.block_number.toLocaleString()}` : "—"}
                  </td>
                  <td>
                    {proof.tx_hash ? (
                      explorerUrl ? (
                        <a
                          href={explorerUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:text-violet transition-colors"
                        >
                          <Hash value={proof.tx_hash} />
                        </a>
                      ) : (
                        <Hash value={proof.tx_hash} />
                      )
                    ) : (
                      <span className="font-mono text-micro uppercase text-dim">
                        {settlementLabel(proof.submission_status)}
                      </span>
                    )}
                  </td>
                  <td className="font-mono text-micro uppercase text-dim">{proof.agent_role}</td>
                  <td className="font-mono text-xs text-dim whitespace-nowrap">
                    {timeAgo(proof.recorded_at)}
                  </td>
                  <td className="text-right">
                    <button
                      onClick={() => verify(proof.task_id)}
                      disabled={verifying === proof.task_id}
                      className="btn-ghost"
                    >
                      {verifying === proof.task_id ? "Verifying…" : "Verify"}
                    </button>
                  </td>
                </tr>
                {result && (
                  <tr>
                    <td colSpan={5} className="bg-raise">
                      <VerifyResult result={result} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
