import { motion } from "framer-motion";
import { ArrowLeft, AlertCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { api } from "../lib/api";
import { ProofLedger } from "../components/economy/ProofLedger";
import { badgeStyle } from "../components/economy/Leaderboard";

function truncate(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] text-ink-muted uppercase tracking-wide">{label}</span>
        <span className="text-[11px] font-mono text-ink-dim">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-white overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-accent to-cyan"
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
}

export function AgentDetail() {
  const { role = "" } = useParams();
  const nav = useNavigate();

  const { data, error, isLoading } = useSWR(
    `/api/economy/agents/${role}`,
    () => api.getAgentDetail(role),
    { refreshInterval: 5000 }
  );

  return (
    <div className="relative min-h-screen" style={{ background: "#FFFDFB" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />

        <div className="border-b border-ink/[0.09] bg-white backdrop-blur-md">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
            <button
              onClick={() => nav("/app/economy")}
              className="flex items-center gap-1.5 text-ink-muted hover:text-ink text-xs font-medium transition-colors shrink-0"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Economy
            </button>
          </div>
        </div>

        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <div className="w-6 h-6 rounded-full border-2 border-ink/[0.09] border-t-white animate-spin" />
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-danger shrink-0" />
              <p className="text-sm text-red-400">Couldn't load this agent's passport.</p>
            </div>
          )}

          {data && (
            <>
              <motion.div
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                className="card p-6 mb-8"
              >
                <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
                  <div>
                    <h1
                      className="font-display font-bold text-ink capitalize mb-1"
                      style={{ fontSize: "clamp(1.6rem, 3.5vw, 2.2rem)" }}
                    >
                      {data.passport.role}
                    </h1>
                    <p className="text-xs font-mono text-ink-muted">
                      AgentPassport #{data.passport.token_id} · {truncate(data.passport.owner_address)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-widest px-2.5 py-1.5 rounded-full border ${badgeStyle(data.reputation?.badge ?? "Bronze")}`}
                    >
                      {data.reputation?.badge ?? "Bronze"}
                    </span>
                    <div className="text-right">
                      <p className="font-mono text-2xl font-bold text-cyan leading-none">
                        {data.reputation?.composite ?? 0}
                      </p>
                      <p className="text-[10px] text-ink-muted uppercase tracking-wide">Composite</p>
                    </div>
                  </div>
                </div>

                <div className="grid sm:grid-cols-3 gap-5">
                  <ScoreBar label="Success" value={data.reputation?.success_rate ?? 0} />
                  <ScoreBar label="Speed" value={data.reputation?.speed ?? 0} />
                  <ScoreBar label="Volume" value={data.reputation?.volume ?? 0} />
                </div>

                <div className="mt-6 pt-5 border-t border-ink/[0.09] flex flex-wrap gap-1.5">
                  {data.passport.capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white text-ink-dim border border-ink/[0.09]"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </motion.div>

              <h2 className="text-sm font-semibold text-ink uppercase tracking-widest mb-4">
                Proof History
              </h2>
              <ProofLedger proofs={data.proofs ?? []} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
