import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { Shell } from "../components/AppNav";
import { api } from "../lib/api";
import { useEconomySSE } from "../lib/sse";
import { Leaderboard } from "../components/economy/Leaderboard";
import { PassportCard } from "../components/economy/PassportCard";
import { ProofLedger } from "../components/economy/ProofLedger";
import { Empty, Micro, PageHead, Panel, ProofBlock, Tabs } from "../components/ui";

type Tab = "leaderboard" | "passports" | "ledger";

const TABS: { id: Tab; label: string }[] = [
  { id: "leaderboard", label: "Leaderboard" },
  { id: "passports", label: "Passports" },
  { id: "ledger", label: "Proof ledger" },
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
    <Shell>
      <PageHead marker="ECONOMY — AGENT LEDGER" title="The agent economy">
        Every completed task mints a proof of work and bumps its agent's on-chain reputation, live.
      </PageHead>

      {/* The signature: on-chain proof, stated once, inverted into a solid violet field. */}
      <div className="proof-field flex flex-col sm:flex-row sm:items-stretch mb-8">
        <div className="flex items-center gap-6 px-6 py-6 flex-1">
          <ProofBlock className="w-16 h-16 shrink-0 text-on-violet" />
          <div>
            <Micro>{chain?.network ?? "Chain"}</Micro>
            <p className="font-display font-bold tracking-tightest text-2xl mt-1.5 leading-none">
              Chain ID {chain?.chainId ?? "—"}
            </p>
          </div>
        </div>
        <div className="flex border-t sm:border-t-0 sm:border-l border-line/20">
          <div className="px-6 py-6">
            <Micro>Proofs shown</Micro>
            <p className="font-display font-bold tabular text-3xl mt-1.5 leading-none">
              {proofs?.length ?? 0}
            </p>
          </div>
          <div className="px-6 py-6 border-l border-line/20">
            <Micro>Block height</Micro>
            <p className="font-display font-bold tabular text-3xl mt-1.5 leading-none">
              {topBlock > 0 ? `#${topBlock.toLocaleString()}` : "—"}
            </p>
          </div>
        </div>
      </div>

      <div className="mb-6 border-b border-line">
        <Tabs value={tab} onChange={setTab} options={TABS} />
      </div>

      {tab === "leaderboard" && (
        <Panel title="Agent leaderboard">
          <Leaderboard entries={leaderboard ?? []} />
        </Panel>
      )}

      {tab === "passports" &&
        (passports && passports.length > 0 ? (
          <div className="grid sm:grid-cols-2 gap-4">
            {passports.map((p) => (
              <PassportCard key={p.role} passport={p} />
            ))}
          </div>
        ) : (
          <Panel>
            <Empty title="No passports minted yet">
              Completing a task mints an agent's first passport.
            </Empty>
          </Panel>
        ))}

      {tab === "ledger" && (
        <Panel title="Proof ledger">
          <ProofLedger proofs={proofs ?? []} chain={chainStatus} />
        </Panel>
      )}
    </Shell>
  );
}
