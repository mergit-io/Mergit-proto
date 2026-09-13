import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Shell } from "../components/AppNav";
import { Empty, Micro, Notice, PageHead, Panel } from "../components/ui";

const BASE = "/api";

async function fetchWorkflows(repo: string) {
  const r = await fetch(`${BASE}/actions/workflows?repo=${encodeURIComponent(repo)}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function fetchProtection(repo: string) {
  const r = await fetch(`${BASE}/actions/protection?repo=${encodeURIComponent(repo)}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function createActionGoal(repo: string, instruction: string) {
  const r = await fetch(`${BASE}/actions/goal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo, instruction }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

const QUICK_ACTIONS = [
  { label: "Add CI (pytest)", instruction: "Add a GitHub Actions CI workflow that runs pytest on every push and pull request to the main branch." },
  { label: "Add CI (npm test)", instruction: "Add a GitHub Actions CI workflow that runs npm test on every push and pull request." },
  { label: "Add lint workflow", instruction: "Add a GitHub Actions workflow that runs ruff and mypy on every push for code quality." },
  { label: "Require PR reviews", instruction: "Enable branch protection on the default branch: require at least 1 approving review before merging and dismiss stale reviews." },
  { label: "Enforce status checks", instruction: "Enable branch protection: require status checks to pass before merging, with strict mode enabled." },
  { label: "Add release workflow", instruction: "Add a GitHub Actions release workflow that creates a GitHub Release and uploads build artifacts when a tag is pushed." },
  { label: "Add Dependabot", instruction: "Add a Dependabot configuration file to auto-update Python pip and GitHub Actions dependencies weekly." },
];

function WorkflowCard({ wf }: { wf: { name: string; path: string; content: string } }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-raise transition-colors"
      >
        <span className="flex-1 text-sm text-text truncate">{wf.name}</span>
        <span className="font-mono text-micro text-faint hidden sm:block">{wf.path}</span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-dim shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-dim shrink-0" />
        )}
      </button>
      {open && (
        <pre className="font-mono text-xs bg-raise border border-line p-4 overflow-x-auto whitespace-pre-wrap text-dim">
          {wf.content}
        </pre>
      )}
    </div>
  );
}

function ProtectionRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-line-soft last:border-0">
      <Micro>{label}</Micro>
      <span className="text-sm text-text">{value}</span>
    </div>
  );
}

function ProtectionBool({ v }: { v: boolean }) {
  return <span className={v ? "text-mint" : "text-dim"}>{v ? "Yes" : "No"}</span>;
}

function ProtectionCard({ data }: { data: { protected: boolean; branch: string; rules: Record<string, unknown> } }) {
  const rules = data.rules as {
    enforce_admins?: boolean;
    required_status_checks?: { strict: boolean; contexts: string[] } | null;
    required_pull_request_reviews?: { dismiss_stale_reviews: boolean; require_code_owner_reviews: boolean; required_approving_review_count: number } | null;
  };
  return (
    <div>
      <div className="px-4 py-2.5 border-b border-line-soft">
        <Micro className={data.protected ? "text-mint" : "text-dim"}>
          {data.protected ? "Protected" : "Unprotected"}
        </Micro>
      </div>
      {data.protected ? (
        <>
          <ProtectionRow label="Enforce admins" value={<ProtectionBool v={!!rules.enforce_admins} />} />
          <ProtectionRow
            label="Required status checks"
            value={
              rules.required_status_checks ? (
                <span className="text-mint">{rules.required_status_checks.contexts.length} context(s)</span>
              ) : (
                <ProtectionBool v={false} />
              )
            }
          />
          <ProtectionRow
            label="Required PR reviews"
            value={
              rules.required_pull_request_reviews ? (
                <span className="text-mint">{rules.required_pull_request_reviews.required_approving_review_count} reviewer(s)</span>
              ) : (
                <ProtectionBool v={false} />
              )
            }
          />
          {rules.required_pull_request_reviews && (
            <>
              <ProtectionRow label="Dismiss stale reviews" value={<ProtectionBool v={rules.required_pull_request_reviews.dismiss_stale_reviews} />} />
              <ProtectionRow label="Require code owner reviews" value={<ProtectionBool v={rules.required_pull_request_reviews.require_code_owner_reviews} />} />
            </>
          )}
        </>
      ) : (
        <p className="px-4 py-5 text-sm text-dim">No branch protection rules configured.</p>
      )}
    </div>
  );
}

export function Actions() {
  const nav = useNavigate();
  const [repo, setRepo] = useState("");
  const [loadedRepo, setLoadedRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const [workflows, setWorkflows] = useState<{ name: string; path: string; content: string }[] | null>(null);
  const [protection, setProtection] = useState<{ protected: boolean; branch: string; rules: Record<string, unknown> } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [instruction, setInstruction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [submitErr, setSubmitErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!repo.trim()) return;
    setLoading(true);
    setLoadErr(null);
    setWorkflows(null);
    setProtection(null);
    setSubmitted(null);
    try {
      const [wf, prot] = await Promise.all([fetchWorkflows(repo.trim()), fetchProtection(repo.trim())]);
      setWorkflows(wf.workflows ?? []);
      setProtection(prot);
      setLoadedRepo(repo.trim());
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : "Could not load this repository. Check the name and try again.");
    } finally {
      setLoading(false);
    }
  }, [repo]);

  const submit = async (instr: string) => {
    if (!loadedRepo || !instr.trim()) return;
    setSubmitting(true);
    setSubmitErr(null);
    setSubmitted(null);
    try {
      const data = await createActionGoal(loadedRepo, instr.trim());
      setSubmitted(data.goal_id);
    } catch (e) {
      setSubmitErr(e instanceof Error ? e.message : "Could not delegate this change. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Shell>
      <PageHead marker="AUTOMATION — GITHUB ACTIONS" title="Automate your CI/CD">
        Inspect workflows and branch protection rules. Describe a change and agents write the
        config, open a pull request, and set the rules.
      </PageHead>

      <div className="flex flex-col gap-6">
        <Panel title="Repository">
          <div className="p-4">
            <div className="flex gap-3">
              <input
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()}
                placeholder="owner/repo — e.g. MaskedBug601/Nothing"
                className="field font-mono flex-1"
              />
              <button onClick={load} disabled={loading || !repo.trim()} className="btn-primary shrink-0">
                {loading ? "Loading…" : "Load"}
              </button>
            </div>
            {loadErr && (
              <div className="mt-3">
                <Notice onDismiss={() => setLoadErr(null)}>{loadErr}</Notice>
              </div>
            )}
          </div>
        </Panel>

        {loadedRepo && workflows !== null && protection !== null && (
          <div className="grid lg:grid-cols-2 gap-6">
            <Panel title="Workflows" right={<Micro>{workflows.length}</Micro>}>
              {workflows.length === 0 ? (
                <Empty title="No workflows found">
                  Add a workflow file under .github/workflows to see it here.
                </Empty>
              ) : (
                <div className="divide-y divide-line-soft">
                  {workflows.map((wf) => (
                    <WorkflowCard key={wf.path} wf={wf} />
                  ))}
                </div>
              )}
            </Panel>

            <Panel
              title="Branch protection"
              right={<span className="font-mono text-micro uppercase">{protection.branch}</span>}
            >
              <ProtectionCard data={protection} />
            </Panel>
          </div>
        )}

        <Panel
          title="Automate"
          right={loadedRepo ? <span className="font-mono text-micro uppercase text-dim">{loadedRepo}</span> : undefined}
        >
          <div className="p-4">
            {!loadedRepo && <p className="text-sm text-dim mb-4">Load a repository first, then describe what to change.</p>}

            <div className="flex flex-wrap gap-2 mb-4">
              {QUICK_ACTIONS.map((qa) => (
                <button
                  key={qa.label}
                  onClick={() => setInstruction(qa.instruction)}
                  className={`font-mono text-micro uppercase px-3 py-1.5 border transition-colors ${
                    instruction === qa.instruction
                      ? "border-violet text-violet"
                      : "border-line text-dim hover:text-text hover:border-faint"
                  }`}
                >
                  {qa.label}
                </button>
              ))}
            </div>

            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder={
                loadedRepo
                  ? 'Describe what you want — e.g. "Add a CI workflow that runs pytest on every push"'
                  : "Load a repository above first, then describe what to automate…"
              }
              rows={4}
              className="field resize-none mb-4"
            />

            <div className="flex items-center gap-3">
              <button
                onClick={() => submit(instruction)}
                disabled={submitting || !instruction.trim() || !loadedRepo}
                className="btn-primary"
              >
                {submitting ? "Delegating…" : "Delegate"}
              </button>
              {submitErr && <p className="text-sm text-red">{submitErr}</p>}
            </div>

            {submitted && (
              <div className="mt-4">
                <Notice tone="done">
                  Delegated — agents are on it ({submitted}).{" "}
                  <button onClick={() => nav(`/app/goals/${submitted}`)} className="underline hover:no-underline">
                    Watch live →
                  </button>
                </Notice>
              </div>
            )}
          </div>
        </Panel>

        {!loadedRepo && !loading && (
          <Panel title="Workflows and rules">
            <Empty title="Load a repository">
              Enter a repository above to inspect its CI/CD workflows and branch protection rules.
            </Empty>
          </Panel>
        )}
      </div>
    </Shell>
  );
}
