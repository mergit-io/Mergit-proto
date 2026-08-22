import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import useSWR, { mutate } from "swr";
import { api } from "../lib/api";
import type { GoalSummary } from "../lib/api";
import { GoalRow } from "../components/GoalCard";
import { GoalInput } from "../components/GoalInput";
import { Shell } from "../components/AppNav";
import {
  Empty,
  Hash,
  Loading,
  Metric,
  MetricRow,
  Micro,
  Notice,
  Panel,
  ProofBlock,
  Tabs,
  settlementLabel,
} from "../components/ui";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "running", label: "Running" },
  { id: "done", label: "Done" },
  { id: "failed", label: "Failed" },
] as const;
type Filter = (typeof FILTERS)[number]["id"];

const ACTIVE = ["NEW", "PLANNING", "RUNNING"];

/** How many receipts this panel has room to list. */
const RECEIPTS = 4;
/** The window the economy page reads. Matched deliberately — see below. */
const PROOF_WINDOW = 50;

/** The signature panel: proof settlement, inverted into a solid violet field. */
function ProofField() {
  // SWR caches on the key alone. This asked for 4 under the same key the economy page
  // uses for 50, so the two clobbered each other and the count read whichever landed
  // last. Asking for the same window makes the shared cache correct rather than a
  // collision, and the panel slices what it has room to show.
  const { data: proofs } = useSWR(
    "/api/economy/proofs",
    () => api.getProofs(PROOF_WINDOW),
    { refreshInterval: 5000 }
  );
  const { data: chain } = useSWR("/api/economy/chain/status", () => api.getChainStatus(), {
    refreshInterval: 15000,
  });

  const minted = proofs?.length ?? 0;
  const pending = chain?.outbox?.pending ?? 0;

  return (
    <div className="proof-field flex flex-col h-full">
      <div className="px-5 pt-5 pb-6">
        <Micro>Proof of work</Micro>
        <p className="font-display font-bold tracking-tightest text-3xl leading-[1.05] mt-3">
          Every task
          <br />
          settles on chain.
        </p>
      </div>

      <div className="flex-1 flex items-center justify-center py-6 min-h-[120px]">
        <ProofBlock className="w-28 h-28 text-on-violet" />
      </div>

      <div className="grid grid-cols-2 border-t border-line/25">
        <div className="px-5 py-4 border-r border-line/25">
          <Micro>Proofs shown</Micro>
          <p className="font-display font-bold tabular text-3xl mt-1.5 leading-none">{minted}</p>
        </div>
        <div className="px-5 py-4">
          <Micro>Queued</Micro>
          <p className="font-display font-bold tabular text-3xl mt-1.5 leading-none">{pending}</p>
        </div>
      </div>

      <div className="border-t border-line/25">
        <div className="px-5 py-2.5">
          <Micro>Latest receipts</Micro>
        </div>
        {proofs && proofs.length > 0 ? (
          <ul className="pb-2">
            {proofs.slice(0, RECEIPTS).map((p) => (
              <li key={p.task_id} className="flex items-center justify-between px-5 py-1.5 text-xs">
                {/* Only a settled proof has a transaction hash. Until then the row says so
                    rather than showing the locally minted stand-in as if it were one. */}
                {p.tx_hash ? (
                  <Hash value={p.tx_hash} />
                ) : (
                  <span className="font-mono text-micro uppercase opacity-70">
                    {settlementLabel(p.submission_status)}
                  </span>
                )}
                <span className="font-mono text-micro uppercase opacity-70">{p.agent_role}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 pb-5 text-xs opacity-70">
            No proofs yet. Completing a task mints the first one.
          </p>
        )}
      </div>
    </div>
  );
}

/** Who is available to take work, and how well each has performed so far. */
function Roster() {
  const { data } = useSWR("/api/economy/leaderboard", () => api.getLeaderboard(), {
    refreshInterval: 10000,
  });

  return (
    <Panel
      title="Agent roster"
      right={
        <Link to="/app/economy" className="micro hover:text-text transition-colors">
          Economy →
        </Link>
      }
    >
      {data && data.length > 0 ? (
        <ul>
          {data.map((a) => (
            <li
              key={a.role}
              className="flex items-center justify-between px-4 py-2.5 border-b border-line-soft last:border-0"
            >
              <span className="font-mono text-micro uppercase">{a.role}</span>
              <span className="font-mono text-micro uppercase text-dim tabular">
                {Math.round(a.composite)} rep
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-5 text-xs text-dim">
          Agents register a passport the first time they finish a task.
        </p>
      )}
    </Panel>
  );
}

export function Dashboard() {
  const nav = useNavigate();
  const { data, isLoading } = useSWR("/api/goals", () => api.listGoals(), {
    refreshInterval: 3000,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const submit = async (goal: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitGoal(goal);
      await mutate("/api/goals");
      nav(`/app/goals/${res.goal_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The goal could not be submitted. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const goals: GoalSummary[] = data?.goals ?? [];
  const running = goals.filter((g) => ACTIVE.includes(g.status)).length;
  const done = goals.filter((g) => g.status === "COMPLETED").length;
  const failed = goals.filter((g) => g.status === "FAILED").length;

  const shown = goals.filter((g) => {
    if (filter === "all") return true;
    if (filter === "running") return ACTIVE.includes(g.status);
    if (filter === "done") return g.status === "COMPLETED";
    return g.status === "FAILED";
  });

  return (
    <Shell wide>
      {/* Delegate console — the page's single job, stated at full size. */}
      <div className="grid lg:grid-cols-[1fr_360px] gap-px mb-px">
        <div className="panel px-6 py-8 lg:px-10 lg:py-12">
          <Micro>Step 01 — Delegate</Micro>
          <h1 className="font-display font-bold tracking-tightest leading-[0.92] mt-4 mb-4 text-[clamp(2.25rem,5vw,3.75rem)]">
            What should the
            <br />
            swarm do?
          </h1>
          <p className="text-sm text-dim max-w-md leading-relaxed mb-8">
            One sentence is enough. Mergit decomposes it into a task graph, assigns specialised
            agents, and mints a proof for every completed step.
          </p>

          <GoalInput onSubmit={submit} loading={submitting} />

          {error && (
            <div className="mt-4">
              <Notice onDismiss={() => setError(null)}>{error}</Notice>
            </div>
          )}
        </div>

        <ProofField />
      </div>

      <MetricRow>
        <Metric label="Active" value={running} />
        <Metric label="Completed" value={done} />
        <Metric label="Failed" value={failed} />
        <Metric label="Total goals" value={goals.length} accent />
      </MetricRow>

      <div className="grid lg:grid-cols-[1fr_320px] gap-6 mt-6 items-start">
        <Panel
          title="Recent goals"
          right={<Tabs value={filter} onChange={setFilter} options={FILTERS} />}
        >
          {isLoading && <Loading label="Loading goals" />}

          {!isLoading && goals.length === 0 && (
            <Empty title="No goals yet">
              Describe an outcome above. The orchestrator plans the steps, so you never write them
              out yourself.
            </Empty>
          )}

          {!isLoading && goals.length > 0 && shown.length === 0 && (
            <Empty title={`Nothing ${filter}`}>Switch the filter to see the other goals.</Empty>
          )}

          {shown.length > 0 && (
            <table className="dtable">
              <thead>
                <tr>
                  <th>Goal</th>
                  <th>Submitted</th>
                  <th>ID</th>
                  <th className="text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((g) => (
                  <GoalRow key={g.goal_id} goal={g} />
                ))}
              </tbody>
            </table>
          )}

          {/* Without this the list reads as the whole history when it is a page of it. */}
          {!isLoading && data && data.total > goals.length && (
            <div className="border-t border-line px-4 py-2.5">
              <Micro>
                Showing {goals.length} of {data.total} goals
              </Micro>
            </div>
          )}
        </Panel>

        <Roster />
      </div>
    </Shell>
  );
}
