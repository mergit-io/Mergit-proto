import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Loader2, ShieldAlert, X } from "lucide-react";
import { AppBackground } from "../components/AppBackground";
import { AppNav } from "../components/AppNav";
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
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />
      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />
        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          <header className="mb-8">
            <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
              <ShieldAlert className="w-5 h-5" /> Approvals
            </h1>
            <p className="mt-2 text-sm text-white/50 max-w-2xl">
              Agents pause here before anything they cannot undo — merging a pull request,
              creating a repository, changing branch protection. Everything else runs without
              asking.
            </p>
          </header>

          {pending.length === 0 ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-8 text-center">
              <p className="text-sm text-white/50">Nothing is waiting on you.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pending.map((a) => (
                <article key={a.id} className="rounded-2xl border border-amber-400/20 bg-amber-400/[0.04] p-5">
                  <p className="text-sm text-white">{a.summary}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-white/40">
                    <Link to={`/app/goals/${a.goal_id}`} className="underline underline-offset-2 hover:text-white/70">
                      View the goal
                    </Link>
                    <span>·</span>
                    <span>expires {new Date(a.expires_at * 1000).toLocaleString()}</span>
                  </div>

                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-white/35 hover:text-white/60">
                      Exact request
                    </summary>
                    {/* The approval is bound to a hash of these arguments, so what is shown
                        here is precisely what gets authorised — a re-plan with different
                        arguments produces a new prompt rather than reusing this decision. */}
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-black/40 p-3 text-[11px] text-white/50">
                      {a.tool_name}({a.args_json})
                    </pre>
                  </details>

                  <div className="mt-4 flex gap-2">
                    <button
                      onClick={() => decide(a.id, "approve")}
                      disabled={busy === a.id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5
                                 text-xs font-medium text-black hover:bg-white/90 disabled:opacity-50"
                    >
                      {busy === a.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      Approve
                    </button>
                    <button
                      onClick={() => decide(a.id, "deny")}
                      disabled={busy === a.id}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5
                                 text-xs text-white/60 hover:border-red-400/30 hover:text-red-300 disabled:opacity-50"
                    >
                      <X className="w-3 h-3" /> Decline
                    </button>
                  </div>
                  {/* Said before the click, not after. A denial cannot be walked back by
                      the agent trying again, and the user should know that going in. */}
                  <p className="mt-2 text-[11px] text-white/25">
                    Declining is final — the agent reports it and moves on.
                  </p>
                </article>
              ))}
            </div>
          )}

          {recent.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-white/35">
                Decided
              </h2>
              <ul className="space-y-1.5">
                {recent.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 rounded-lg border border-white/[0.06] px-4 py-2.5 text-sm">
                    <span className={a.decision === "approve" ? "text-emerald-400" : "text-white/30"}>
                      {a.decision === "approve" ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                    </span>
                    <span className="flex-1 text-white/60">{a.summary}</span>
                    <span className="text-xs text-white/25">
                      {new Date(a.created_at * 1000).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
