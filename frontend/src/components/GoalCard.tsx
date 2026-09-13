import { Link } from "react-router-dom";
import type { GoalSummary } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

export function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

/** One goal, as a row in the recent-goals table.
 *
 *  The row keeps its `row` semantics and the link lives in the first cell, stretched
 *  across the row by a positioned ::after. `role="link"` on the `<tr>` read better in
 *  markup but replaced the row role, which orphaned the cells from their column headers,
 *  and a div-with-onClick cannot be opened in a new tab or middle-clicked. */
export function GoalRow({ goal }: { goal: GoalSummary }) {
  return (
    <tr className="row-link relative cursor-pointer">
      <td className="max-w-0">
        <Link
          to={`/app/goals/${goal.goal_id}`}
          className="truncate font-medium block after:absolute after:inset-0 after:content-['']"
        >
          {goal.title}
        </Link>
      </td>
      <td className="w-32 font-mono text-micro uppercase text-dim whitespace-nowrap">
        {timeAgo(goal.created_at)}
      </td>
      <td className="w-40">
        <span className="font-mono text-xs text-dim tabular">{goal.goal_id.slice(0, 8)}</span>
      </td>
      <td className="w-28 text-right">
        <StatusBadge status={goal.status} />
      </td>
    </tr>
  );
}
