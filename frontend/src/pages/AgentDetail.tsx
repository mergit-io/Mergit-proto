import { useParams } from "react-router-dom";
import useSWR from "swr";
import { Shell } from "../components/AppNav";
import { api } from "../lib/api";
import { ProofLedger } from "../components/economy/ProofLedger";
import { badgeStyle } from "../components/economy/Leaderboard";
import { BackLink, Hash, Loading, Metric, Micro, Notice, PageHead, Panel } from "../components/ui";

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <Micro>{label}</Micro>
        <span className="font-mono text-xs tabular text-dim">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1 bg-line-soft">
        <div className="h-full bg-violet" style={{ width: `${Math.min(100, value * 100)}%` }} />
      </div>
    </div>
  );
}

export function AgentDetail() {
  const { role = "" } = useParams();

  const { data, error, isLoading } = useSWR(
    `/api/economy/agents/${role}`,
    () => api.getAgentDetail(role),
    { refreshInterval: 5000 }
  );

  return (
    <Shell>
      <div className="mb-6">
        <BackLink to="/app/economy">Economy</BackLink>
      </div>

      {isLoading && <Loading label="Loading passport" />}

      {/* SWR keeps the last good `data` when a background refresh fails and sets `error` at
          the same time, so `error` on its own does not mean the passport is unavailable — it
          means the newest poll did not land. Rendering this unconditionally put "could not be
          loaded" directly above a fully populated passport, which was simply untrue. */}
      {error && !data && <Notice>This agent's passport could not be loaded.</Notice>}
      {error && data && (
        <Notice tone="wait">
          Showing the passport as it was last loaded — the live refresh is not getting through.
        </Notice>
      )}

      {data && (
        <>
          <PageHead marker="ECONOMY — AGENT" title={<span className="capitalize">{data.passport.role}</span>}>
            Passport #{data.passport.token_id} · <Hash value={data.passport.owner_address} />
          </PageHead>

          {/* The signature: composite on-chain reputation, the one score that matters. */}
          <div className="grid lg:grid-cols-[1fr_320px] gap-px mb-8">
            <div className="panel p-6 lg:p-8">
              <div className="mb-6">
                <span className={`micro border px-2 py-1 ${badgeStyle(data.reputation?.badge ?? "Bronze")}`}>
                  {data.reputation?.badge ?? "Bronze"}
                </span>
              </div>

              <div className="grid sm:grid-cols-3 gap-6">
                <ScoreBar label="Success" value={data.reputation?.success_rate ?? 0} />
                <ScoreBar label="Speed" value={data.reputation?.speed ?? 0} />
                <ScoreBar label="Volume" value={data.reputation?.volume ?? 0} />
              </div>

              <div className="mt-6 pt-5 border-t border-line-soft flex flex-wrap gap-1.5">
                {data.passport.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="font-mono text-micro px-1.5 py-0.5 border border-line-soft text-dim"
                  >
                    {cap}
                  </span>
                ))}
                {data.passport.capabilities.length === 0 && (
                  <span className="micro">No tools registered</span>
                )}
              </div>
            </div>

            <Metric
              label="Composite reputation"
              value={data.reputation?.composite ?? 0}
              sub={<Hash value={data.passport.did} />}
              accent
            />
          </div>

          <Panel title="Proof history">
            <ProofLedger proofs={data.proofs ?? []} />
          </Panel>
        </>
      )}
    </Shell>
  );
}
