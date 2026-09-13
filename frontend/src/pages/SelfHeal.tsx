import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { Shell } from "../components/AppNav";
import { api } from "../lib/api";
import type { HealAttempt } from "../lib/api";
import { Empty, Hash, Metric, MetricRow, PageHead, Panel, Status } from "../components/ui";

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const STATUS_LABEL: Record<string, string> = {
  filed: "Issue filed",
  simulated: "Simulated",
};

const OUTCOME_LABEL: Record<string, string> = {
  fixed: "Fixed",
  failed: "Fix failed",
  abandoned: "Abandoned",
};

function AttemptRow({
  attempt,
  onOpenGoal,
}: {
  attempt: HealAttempt;
  onOpenGoal: (goalId: string) => void;
}) {
  return (
    <tr>
      <td className="font-mono text-micro uppercase">{attempt.agent_name}</td>
      <td className="font-mono text-xs text-dim max-w-xs truncate">{attempt.error_summary}</td>
      <td>
        <div className="flex flex-wrap items-center gap-2">
          <Status status={attempt.status} label={STATUS_LABEL[attempt.status] ?? attempt.status} />
          {attempt.outcome && (
            <Status
              status={attempt.outcome}
              label={OUTCOME_LABEL[attempt.outcome] ?? attempt.outcome}
            />
          )}
          {attempt.recurrence_count > 1 && (
            <span className="micro border border-violet text-violet px-1.5 py-0.5">
              Seen {attempt.recurrence_count}×
            </span>
          )}
        </div>
      </td>
      <td>
        <Hash value={attempt.fingerprint} />
      </td>
      <td className="whitespace-nowrap">
        {attempt.issue_url && (
          <a
            href={attempt.issue_url}
            target="_blank"
            rel="noreferrer"
            className="micro hover:text-text transition-colors mr-3"
          >
            Issue #{attempt.issue_number}
          </a>
        )}
        {attempt.fix_goal_id && (
          <button
            onClick={() => onOpenGoal(attempt.fix_goal_id!)}
            className="micro hover:text-text transition-colors"
          >
            View fix goal
          </button>
        )}
      </td>
      <td className="text-right font-mono text-xs text-dim tabular whitespace-nowrap">
        {timeAgo(attempt.created_at)}
      </td>
    </tr>
  );
}

export function SelfHeal() {
  const nav = useNavigate();
  const { data: attempts } = useSWR("/api/heal/attempts", () => api.getHealAttempts(), {
    refreshInterval: 5000,
  });
  const { data: stats } = useSWR("/api/heal/stats", () => api.getHealStats(), {
    refreshInterval: 5000,
  });

  return (
    <Shell>
      <PageHead marker="RELIABILITY — SELF-HEAL" title="Self-heal">
        When a run fails from a bug in Mergit's own code — not a rate limit or a bad key — the
        system fingerprints the error, files an issue, and spawns an agent pipeline to fix itself.
        Repeat failures deduplicate instead of filing again.
      </PageHead>

      {stats && (
        <div className="mb-8">
          <MetricRow>
            <Metric label="Distinct bugs" value={stats.total} />
            <Metric label="Total occurrences" value={stats.recurrences} />
            <Metric label="Fixed" value={stats.fixed} />
            <Metric label="Issues filed" value={stats.by_status?.filed ?? 0} />
          </MetricRow>
        </div>
      )}

      <Panel title="Repair attempts">
        {!attempts || attempts.length === 0 ? (
          <Empty title="No bugs detected yet">
            Developer-side failures appear here automatically.
          </Empty>
        ) : (
          <table className="dtable">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Error</th>
                <th>Status</th>
                <th>Fingerprint</th>
                <th>Links</th>
                <th className="text-right">Seen</th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((attempt) => (
                <AttemptRow
                  key={attempt.id}
                  attempt={attempt}
                  onOpenGoal={(goalId) => nav(`/app/goals/${goalId}`)}
                />
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </Shell>
  );
}
