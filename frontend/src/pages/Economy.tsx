import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { motion } from "framer-motion";
import { Trophy, Wallet, ScrollText } from "lucide-react";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { api } from "../lib/api";
import { useEconomySSE } from "../lib/sse";
import { Leaderboard } from "../components/economy/Leaderboard";
import { PassportCard } from "../components/economy/PassportCard";
import { ProofLedger } from "../components/economy/ProofLedger";

type Tab = "leaderboard" | "passports" | "ledger";

const TABS: { id: Tab; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "leaderboard", label: "Leaderboard", Icon: Trophy },
  { id: "passports", label: "Passports", Icon: Wallet },
  { id: "ledger", label: "Proof Ledger", Icon: ScrollText },
];

const ECONOMY_KEYS = [
  "/api/economy/leaderboard",
  "/api/economy/passports",
  "/api/economy/proofs",
  "/api/economy/chain",
  "/api/economy/chain/status",
];

export function Economy() {
  const [tab, setTab] = useState<Tab>("leaderboard");

  const { data: leaderboard } = useSWR(ECONOMY_KEYS[0], () => api.getLeaderboard(), { refreshInterval: 5000 });
  const { data: passports } = useSWR(ECONOMY_KEYS[1], () => api.getPassports(), { refreshInterval: 5000 });
  const { data: proofs } = useSWR(ECONOMY_KEYS[2], () => api.getProofs(50), { refreshInterval: 5000 });
  const { data: chain } = useSWR(ECONOMY_KEYS[3], () => api.getChain(), { refreshInterval: 5000 });
  const { data: chainStatus } = useSWR(ECONOMY_KEYS[4], () => api.getChainStatus(), { refreshInterval: 5000 });

  const { count: economyEventCount } = useEconomySSE();

  useEffect(() => {
    if (economyEventCount === 0) return;
    ECONOMY_KEYS.forEach((key) => mutate(key));
  }, [economyEventCount]);

  const topBlock = proofs && proofs.length > 0 ? proofs[0].block_number : 0;

  return (
    <div className="relative min-h-screen" style={{ background: "#FFFDFB" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />

        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          {/* Page header */}
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mb-8"
          >
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/25 bg-accent/8">
                <span className="w-1.5 h-1.5 rounded-full bg-proof animate-pulse-ring" />
                <span className="text-xs font-medium text-accent-2">
                  {chain?.network ?? "Monad Testnet"} · chainId {chain?.chainId ?? 10143}
                </span>
              </div>
              {topBlock > 0 && (
                <span className="text-xs font-mono text-ink-muted">
                  block #{topBlock.toLocaleString()} · {proofs?.length ?? 0} recent proofs
                </span>
              )}
            </div>
            <h1 className="font-display font-bold text-ink mb-3" style={{ fontSize: "clamp(1.8rem, 4vw, 2.6rem)" }}>
              The Agent <span className="text-accent">Economy</span>
            </h1>
            <p className="text-ink-dim text-sm max-w-xl leading-relaxed">
              Every completed task mints a proof-of-work and bumps its agent's on-chain reputation, live.
            </p>
          </motion.div>

          {/* Tabs */}
          <div className="flex items-center gap-1 mb-6 border-b border-ink/[0.09]">
            {TABS.map(({ id, label, Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  tab === id
                    ? "border-accent text-ink"
                    : "border-transparent text-ink-muted hover:text-ink"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {tab === "leaderboard" && <Leaderboard entries={leaderboard ?? []} />}

          {tab === "passports" && (
            <div className="grid sm:grid-cols-2 gap-4">
              {(passports ?? []).map((p, i) => (
                <PassportCard key={p.role} passport={p} index={i} />
              ))}
              {(passports ?? []).length === 0 && (
                <div className="card px-6 py-10 text-center text-ink-muted text-sm sm:col-span-2">
                  No agent passports minted yet.
                </div>
              )}
            </div>
          )}

          {tab === "ledger" && <ProofLedger proofs={proofs ?? []} chain={chainStatus} />}
        </main>
      </div>
    </div>
  );
}
