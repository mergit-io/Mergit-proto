import { useNavigate } from "react-router-dom";
import type { RepEntry } from "../../lib/api";
import { Empty } from "../ui";

/** Badge chip styling — a hairline border tinted by rank, never a filled pill. */
export function badgeStyle(badge: string): string {
  switch (badge) {
    case "Gold":
      return "border-amber text-amber";
    case "Silver":
      return "border-line text-text";
    default:
      return "border-line-soft text-dim";
  }
}

export function Leaderboard({ entries }: { entries: RepEntry[] }) {
  const nav = useNavigate();

  if (entries.length === 0) {
    return (
      <Empty title="No agents have earned reputation yet">
        Run a goal to mint the first proof.
      </Empty>
    );
  }

  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Agent</th>
          <th>Success</th>
          <th>Speed</th>
          <th>Badge</th>
          <th className="text-right">Composite</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <tr
            key={entry.role}
            onClick={() => nav(`/app/economy/agents/${entry.role}`)}
            className="cursor-pointer"
          >
            <td className="font-mono text-xs text-dim tabular">#{entry.rank}</td>
            <td className="font-mono text-micro uppercase">{entry.role}</td>
            <td className="font-mono text-xs tabular text-dim">
              {(entry.success_rate * 100).toFixed(0)}%
            </td>
            <td className="font-mono text-xs tabular text-dim">
              {(entry.speed * 100).toFixed(0)}%
            </td>
            <td>
              <span className={`micro border px-2 py-1 ${badgeStyle(entry.badge)}`}>
                {entry.badge}
              </span>
            </td>
            <td className="text-right">
              <span className="font-mono text-sm font-semibold tabular">{entry.composite}</span>
              <div className="h-1 bg-line-soft mt-1.5 w-24 ml-auto">
                <div
                  className="h-full bg-violet"
                  style={{ width: `${Math.min(100, (entry.composite / 1000) * 100)}%` }}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
