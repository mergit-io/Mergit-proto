import { motion } from "framer-motion";
import { ArrowLeft, AlertCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { api } from "../lib/api";
import { ProofLedger } from "../components/economy/ProofLedger";

function truncate(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function AgentDetail() {
  const { agentName = "" } = useParams();
  const nav = useNavigate();

  const { data, error, isLoading } = useSWR(
    `/api/economy/agents/${agentName}`,
    () => api.getAgentDetail(agentName),
    { refreshInterval: 5000 }
  );

  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />

        <div className="border-b border-white/6 bg-black/40 backdrop-blur-md">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
            <button
              onClick={() => nav("/app/economy")}
              className="flex items-center gap-1.5 text-text-muted hover:text-white text-xs font-medium transition-colors shrink-0"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Economy
            </button>
          </div>
        </div>

        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white animate-spin" />
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
                      className="font-display font-bold text-white capitalize mb-1"
                      style={{ fontSize: "clamp(1.6rem, 3.5vw, 2.2rem)" }}
                    >
                      {data.agent_name}
                    </h1>
                    <p className="text-xs font-mono text-text-muted">{truncate(data.address)}</p>
                  </div>
                  <span className="text-[10px] font-semibold uppercase tracking-widest px-2.5 py-1.5 rounded-full bg-accent/10 text-accent border border-accent/20">
                    Level {data.level}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="font-mono text-2xl font-bold text-cyan">{data.reputation.toLocaleString()}</p>
                    <p className="text-[11px] text-text-muted uppercase tracking-wide">Reputation</p>
                  </div>
                  <div>
                    <p className="font-mono text-2xl font-bold text-proof-green">{data.tasks_completed}</p>
                    <p className="text-[11px] text-text-muted uppercase tracking-wide">Tasks Done</p>
                  </div>
                  <div>
                    <p className="font-mono text-2xl font-bold text-white">{data.tasks_failed}</p>
                    <p className="text-[11px] text-text-muted uppercase tracking-wide">Tasks Failed</p>
                  </div>
                </div>
              </motion.div>

              <h2 className="text-sm font-semibold text-white uppercase tracking-widest mb-4">
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
