import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../components/AppNav";
import { Empty, Micro, PageHead, Panel, Status } from "../components/ui";
import { getCsrfToken } from "../lib/auth";

/**
 * Actions an agent wants to take that it cannot take back.
 *
 * The design constraint that shapes this page: an approval prompt showing a tool name and
 * a JSON blob gets approved reflexively, which is the same as having no gate at all. So
 * the backend renders a sentence — "Merge pull request #12 in acme/api using squash" —
 * and this page shows that sentence and very little else.
 */

interface Approval {
  id: string;
  goal_id: string;
  tool_name: string;
  summary: string;
  args_json: string;
  decision: string | null;
  created_at: number;
  expires_at: number;
}

export function Approvals() {
  const [pending, setPending] = useState<Approval[]>([]);
  const [recent, setRecent] = useState<Approval[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch("/api/approvals", { credentials: "same-origin" });
    if (res.ok) {
      const body = await res.json();
      setPending(body.pending ?? []);
      setRecent((body.recent ?? []).filter((a: Approval) => a.decision));
    }
  }, []);

  useEffect(() => {
    void load();
    // A goal runs for minutes and the tab is often left open on this page waiting.
    const t = setInterval(() => void load(), 10_000);
    return () => clearInterval(t);
  }, [load]);

  const decide = async (id: string, decision: "approve" | "deny") => {
    setBusy(id);
    try {
      await fetch(`/api/approvals/${id}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Mergit-CSRF": getCsrfToken() },
        body: JSON.stringify({ decision }),
      });
      await load();
    } finally {
      setBusy(null);
    }
  };

  return (
    <Shell>
      <PageHead marker="CONTROL — APPROVALS" title="Approvals">
        Agents pause here before anything they cannot undo — merging a pull request, creating a
        repository, changing branch protection. Everything else runs without asking.
      </PageHead>

      <Panel title={`Pending — ${pending.length}`}>
        {pending.length === 0 ? (
          <Empty title="Nothing is waiting on you">
            A request appears here the moment an agent needs your approval to proceed.
          </Empty>
        ) : (
          <ul>
            {pending.map((a) => (
              <li key={a.id} className="border-b border-l-2 border-line-soft border-l-amber px-5 py-5 last:border-b-0">
                <Micro>{a.tool_name}</Micro>
                <p className="text-sm text-text mt-1.5 leading-relaxed">{a.summary}</p>

                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-dim">
                  <Link
                    to={`/app/goals/${a.goal_id}`}
                    className="hover:text-text underline underline-offset-2 transition-colors"
                  >
                    View the goal
                  </Link>
                  <span>Expires {new Date(a.expires_at * 1000).toLocaleString()}</span>
                </div>

                <details className="mt-3">
                  <summary className="cursor-pointer micro hover:text-text transition-colors">
                    Exact request
                  </summary>
                  {/* The approval is bound to a hash of these arguments, so what is shown
                      here is precisely what gets authorised — a re-plan with different
                      arguments produces a new prompt rather than reusing this decision. */}
                  <pre className="mt-2 overflow-x-auto border border-line-soft bg-raise p-3 text-xs font-mono text-dim">
                    {a.tool_name}({a.args_json})
                  </pre>
                </details>

                <div className="mt-4 flex items-center gap-3">
                  <button onClick={() => decide(a.id, "approve")} disabled={busy === a.id} className="btn-primary">
                    Approve
                  </button>
                  <button
                    onClick={() => decide(a.id, "deny")}
                    disabled={busy === a.id}
                    className="btn-ghost border-red text-red hover:border-red hover:text-red"
                  >
                    Decline
                  </button>
                  {busy === a.id && <span className="w-1.5 h-1.5 bg-violet animate-blip" aria-hidden="true" />}
                </div>
                {/* Said before the click, not after. A denial cannot be walked back by
                    the agent trying again, and the user should know that going in. */}
                <p className="mt-2 text-xs text-dim">Declining is final — the agent reports it and moves on.</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {recent.length > 0 && (
        <Panel title="Decided" className="mt-6">
          <ul>
            {recent.map((a) => (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2.5 border-b border-line-soft last:border-0">
                <Status
                  status={a.decision === "approve" ? "APPROVED" : "DENIED"}
                  label={a.decision === "approve" ? "Approved" : "Declined"}
                />
                <span className="flex-1 text-sm text-dim truncate">{a.summary}</span>
                <span className="font-mono text-micro text-faint tabular">
                  {new Date(a.created_at * 1000).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </Shell>
  );
}
