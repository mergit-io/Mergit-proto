import { Link } from "react-router-dom";
import useSWR from "swr";
import { api } from "../lib/api";
import type { ServiceArtifact, ServiceProvider, ServiceRun } from "../lib/api";
import { Shell } from "../components/AppNav";
import { timeAgo } from "../components/GoalCard";
import { Empty, Loading, Metric, MetricRow, Micro, Panel, Status } from "../components/ui";

/**
 * Did the work actually land on every app it was supposed to?
 *
 * Deliberately not the Connections page. That one is about consent — what Mergit may do
 * as you, granted and revoked. This one is about *reach*, and the two fail separately: a
 * connection can be perfectly healthy while every call through it is being refused, and
 * the gap between "connected" and "it worked" is where a silent failure lives.
 *
 * Nothing here comes from an agent's account of its own run. Every number is derived from
 * the `tool_calls` rows, which are written before dispatch and settled with the provider's
 * answer — so a run that claims it posted to Slack and has no Slack row is caught by the
 * difference rather than believed.
 */

const ACCESS: Record<ServiceProvider["access"], { label: string; status: string }> = {
  connected: { label: "Connected", status: "COMPLETED" },
  available: { label: "Not connected", status: "PENDING" },
  // Named plainly rather than shown as "connected": a shared token works for this user and
  // would not work for a second one, and flattening that distinction is how a single-tenant
  // demo comes to look like a multi-tenant product.
  deployment: { label: "Shared token", status: "RUNNING" },
  unconfigured: { label: "Not configured", status: "IDLE" },
};

/** A service, named, with a dot that says whether this run reached it. */
function AppChip({ provider, reached = true }: { provider: string; reached?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 border border-line-soft px-2 py-0.5 font-mono text-micro uppercase text-dim">
      <span className={`w-1.5 h-1.5 ${reached ? "bg-mint" : "bg-faint"}`} />
      {provider}
    </span>
  );
}

function ArtifactLink({ artifact }: { artifact: ServiceArtifact }) {
  return (
    <a
      href={artifact.url}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-xs text-dim hover:text-text underline underline-offset-2 decoration-line transition-colors"
      title={artifact.url}
    >
      {artifact.label}
    </a>
  );
}

function ProviderCard({ p }: { p: ServiceProvider }) {
  const access = ACCESS[p.access];
  const attempted = p.calls.ok + p.calls.failed + p.calls.refused;

  return (
    <Panel
      title={p.label}
      right={<Status status={access.status} label={access.label} />}
      className="h-full flex flex-col"
      bodyClass="p-5 flex-1 flex flex-col"
    >
      <p className="text-sm text-dim leading-relaxed">{p.does}</p>

      {p.account && (
        <p className="mt-3 text-sm text-dim">
          As <span className="text-text">{p.account}</span>
        </p>
      )}

      <div className="grid grid-cols-3 mt-5 border border-line-soft divide-x divide-line-soft">
        <div className="px-3 py-2.5">
          <Micro>Landed</Micro>
          <p className="font-display font-bold tabular text-2xl leading-none mt-1.5 text-mint">
            {p.calls.ok}
          </p>
        </div>
        <div className="px-3 py-2.5">
          <Micro>Failed</Micro>
          <p
            className={`font-display font-bold tabular text-2xl leading-none mt-1.5 ${
              p.calls.failed ? "text-red" : ""
            }`}
          >
            {p.calls.failed}
          </p>
        </div>
        <div className="px-3 py-2.5">
          <Micro>Refused</Micro>
          <p
            className={`font-display font-bold tabular text-2xl leading-none mt-1.5 ${
              p.calls.refused ? "text-amber" : ""
            }`}
          >
            {p.calls.refused}
          </p>
        </div>
      </div>

      {/* A refusal is not a bug — it is a guard doing its job — so it is counted apart
          from a failure rather than folded in with it. */}
      {p.calls.refused > 0 && (
        <p className="mt-2 text-xs text-dim leading-relaxed">
          Refused calls were stopped by a guard or an approval gate before they reached{" "}
          {p.label}.
        </p>
      )}

      <div className="mt-auto pt-5 space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <Micro>{p.tools} tools</Micro>
          <Micro>{p.last_used_at ? `Last used ${timeAgo(p.last_used_at)}` : "Never used"}</Micro>
        </div>
        {p.last_artifact ? (
          // A Notion page title is a sentence. It gets one line and an ellipsis rather
          // than pushing the card taller than the three beside it.
          <p className="flex items-center gap-2 pt-1.5 border-t border-line-soft min-w-0">
            <Micro className="shrink-0">Last landed</Micro>
            <span className="truncate min-w-0">
              <ArtifactLink artifact={p.last_artifact} />
            </span>
          </p>
        ) : attempted > 0 ? (
          <p className="text-xs text-dim pt-1.5 border-t border-line-soft">
            Nothing this service handed back a link to yet.
          </p>
        ) : null}
        {p.access === "available" && (
          <Link to="/app/connections" className="micro hover:text-text transition-colors">
            Connect {p.label} →
          </Link>
        )}
      </div>
    </Panel>
  );
}

function RunRow({ run, all }: { run: ServiceRun; all: string[] }) {
  return (
    <tr>
      <td className="max-w-0">
        <Link to={`/app/goals/${run.goal_id}`} className="truncate font-medium block">
          {run.title}
        </Link>
      </td>
      <td className="w-56">
        <span className="flex flex-wrap gap-1">
          {all.map((key) => (
            <AppChip key={key} provider={key} reached={run.providers.includes(key)} />
          ))}
        </span>
      </td>
      <td className="w-64">
        {run.artifacts.length ? (
          <span className="flex flex-wrap gap-x-3 gap-y-1">
            {run.artifacts.map((a) => (
              <ArtifactLink key={a.url} artifact={a} />
            ))}
          </span>
        ) : (
          <Micro>No links</Micro>
        )}
      </td>
      <td className="w-28 font-mono text-micro uppercase text-dim whitespace-nowrap">
        {timeAgo(run.created_at)}
      </td>
      <td className="w-28 text-right">
        <Status status={run.status} />
      </td>
    </tr>
  );
}

export function Services() {
  // Both endpoints read a window of tool calls and their result bodies, so a tight
  // interval is paid for twice on every tick. Fifteen seconds is still live for a page
  // watched during a run, and it is the difference between a free-tier instance serving
  // the demo and spending its CPU re-reading rows that did not change.
  const { data, isLoading } = useSWR("/api/services", () => api.getServices(10), {
    refreshInterval: 15000,
  });
  const { data: activity } = useSWR("/api/services/activity", () => api.getServiceActivity(25), {
    refreshInterval: 15000,
  });

  const providers = data?.providers ?? [];
  const keys = providers.map((p) => p.key);
  const runs = data?.runs ?? [];

  const reached = providers.filter((p) => p.calls.ok > 0).length;
  const landed = providers.reduce((n, p) => n + p.calls.ok, 0);
  const failed = providers.reduce((n, p) => n + p.calls.failed, 0);
  // The claim this page exists to support, stated as a count rather than as a sentence:
  // runs that did work on more than one service in a single goal.
  const crossApp = runs.filter((r) => r.providers.length > 1).length;

  return (
    <Shell wide>
      <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
        <div className="max-w-2xl">
          <Micro>Reach — services</Micro>
          <h1 className="font-display font-bold tracking-tightest leading-[0.95] mt-3 text-[clamp(2rem,4.5vw,3.25rem)]">
            What landed,
            <br />
            and where.
          </h1>
          <p className="text-sm text-dim mt-4 max-w-xl leading-relaxed">
            Every figure here is read from the call Mergit made and the answer the service
            gave — never from an agent's account of its own run. A service that says it was
            posted to has a link to the thing that was posted.
          </p>
        </div>
        <div className="shrink-0">
          <Link to="/app/connections" className="btn-ghost">
            Manage access →
          </Link>
        </div>
      </header>

      <MetricRow>
        <Metric label="Apps reached" value={`${reached}/${providers.length || 4}`} />
        <Metric label="Calls landed" value={landed} />
        <Metric label="Calls failed" value={failed} />
        <Metric label="Cross-app runs" value={crossApp} accent />
      </MetricRow>

      {isLoading && !data && <Loading label="Reading service calls" />}

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-6 mt-6 items-stretch">
        {providers.map((p) => (
          <ProviderCard key={p.key} p={p} />
        ))}
      </div>

      <div className="mt-6">
        <Panel
          title="Runs, and the apps each one touched"
          right={<Micro>{runs.length} shown</Micro>}
        >
          {runs.length === 0 ? (
            <Empty title="No service calls yet">
              Delegate a goal that starts in one app and ends in another — read a Slack
              thread, open a pull request, file the ticket — and the run appears here with
              a link to each thing it left behind.
            </Empty>
          ) : (
            <table className="dtable">
              <thead>
                <tr>
                  <th>Goal</th>
                  <th>Apps touched</th>
                  <th>Left behind</th>
                  <th>Started</th>
                  <th className="text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <RunRow key={r.goal_id} run={r} all={keys} />
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <div className="mt-6">
        <Panel title="Every service call, newest first" right={<Micro>Last 25</Micro>}>
          {!activity?.uses.length ? (
            <Empty title="Nothing called yet">
              This is the complete log — including calls made on a shared deployment token,
              which the credential audit on the Connections page cannot see.
            </Empty>
          ) : (
            <table className="dtable">
              <thead>
                <tr>
                  <th>When</th>
                  <th>App</th>
                  <th>Tool</th>
                  <th>Goal</th>
                  <th>Left behind</th>
                  <th className="text-right">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {activity.uses.map((u, i) => (
                  <tr key={`${u.ts}-${u.tool}-${i}`}>
                    <td className="w-28 font-mono text-micro uppercase text-dim whitespace-nowrap">
                      {timeAgo(u.ts)}
                    </td>
                    <td className="w-28">
                      <AppChip provider={u.provider} reached={u.outcome === "ok"} />
                    </td>
                    <td className="w-56 font-mono text-xs text-dim">{u.tool}</td>
                    <td className="max-w-0">
                      <Link to={`/app/goals/${u.goal_id}`} className="truncate block">
                        {u.goal_title}
                      </Link>
                    </td>
                    <td className="w-48">
                      {u.url ? (
                        <ArtifactLink artifact={{ provider: u.provider, tool: u.tool, url: u.url, label: u.label }} />
                      ) : (
                        <Micro>—</Micro>
                      )}
                    </td>
                    <td className="w-28 text-right">
                      <Status
                        status={
                          u.outcome === "ok"
                            ? "COMPLETED"
                            : u.outcome === "refused"
                              ? "BLOCKED"
                              : u.outcome === "pending"
                                ? "RUNNING"
                                : "FAILED"
                        }
                        label={u.outcome}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      {data && (
        // Without this the counts read as all time when they are a window on it.
        <p className="mt-4">
          <Micro>
            Counted over the last {data.window} service calls ({data.calls_read} read).
          </Micro>
        </p>
      )}
    </Shell>
  );
}
