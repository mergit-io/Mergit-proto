import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  GitBranch, Shield, Play, RefreshCw, ChevronDown, ChevronRight,
  CheckCircle, XCircle, Loader2, Workflow, Lock, Unlock, Zap
} from "lucide-react";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";

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
    <div className="rounded-xl border border-white/8 bg-white/[0.02] overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/4 transition-colors"
      >
        <Workflow className="w-4 h-4 text-accent shrink-0" />
        <span className="flex-1 text-sm font-medium text-white truncate">{wf.name}</span>
        <span className="text-xs text-text-muted font-mono hidden sm:block">{wf.path}</span>
        {open ? <ChevronDown className="w-4 h-4 text-text-muted ml-1" /> : <ChevronRight className="w-4 h-4 text-text-muted ml-1" />}
      </button>
      {open && (
        <div className="border-t border-white/6 bg-black/30 p-4">
          <pre className="text-xs text-gray-300 font-mono overflow-x-auto leading-relaxed whitespace-pre-wrap">
            {wf.content}
          </pre>
        </div>
      )}
    </div>
  );
}

function ProtectionCard({ data }: { data: { protected: boolean; branch: string; rules: Record<string, unknown> } }) {
  const rules = data.rules as {
    enforce_admins?: boolean;
    required_status_checks?: { strict: boolean; contexts: string[] } | null;
    required_pull_request_reviews?: { dismiss_stale_reviews: boolean; require_code_owner_reviews: boolean; required_approving_review_count: number } | null;
  };

  const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex items-center justify-between py-2.5 border-b border-white/5 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs text-white font-medium">{value}</span>
    </div>
  );

  const Bool = ({ v }: { v: boolean }) => v
    ? <span className="flex items-center gap-1 text-success"><CheckCircle className="w-3 h-3" /> Yes</span>
    : <span className="flex items-center gap-1 text-text-muted"><XCircle className="w-3 h-3" /> No</span>;

  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 mb-3">
        {data.protected
          ? <Lock className="w-4 h-4 text-success" />
          : <Unlock className="w-4 h-4 text-text-muted" />}
        <span className="text-sm font-semibold text-white">{data.branch}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
          data.protected
            ? "text-success border-success/30 bg-success/8"
            : "text-text-muted border-white/10 bg-white/4"
        }`}>
          {data.protected ? "Protected" : "Unprotected"}
        </span>
      </div>
      {data.protected ? (
        <>
          <Row label="Enforce admins" value={<Bool v={!!rules.enforce_admins} />} />
          <Row label="Required status checks" value={
            rules.required_status_checks
              ? <span className="text-success">{rules.required_status_checks.contexts.length} context(s)</span>
              : <Bool v={false} />
          } />
          <Row label="Required PR reviews" value={
            rules.required_pull_request_reviews
              ? <span className="text-success">{rules.required_pull_request_reviews.required_approving_review_count} reviewer(s)</span>
              : <Bool v={false} />
          } />
          {rules.required_pull_request_reviews && (
            <>
              <Row label="Dismiss stale reviews" value={<Bool v={rules.required_pull_request_reviews.dismiss_stale_reviews} />} />
              <Row label="Require code owner reviews" value={<Bool v={rules.required_pull_request_reviews.require_code_owner_reviews} />} />
            </>
          )}
        </>
      ) : (
        <p className="text-xs text-text-muted">No branch protection rules configured.</p>
      )}
    </div>
  );
}

function SectionCard({ delay = 0, children, className = "" }: { delay?: number; children: React.ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={`rounded-2xl border border-white/8 bg-white/[0.02] p-6 backdrop-blur-sm ${className}`}
    >
      {children}
    </motion.div>
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
      setLoadErr(e instanceof Error ? e.message : "Failed to load repo data");
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
      setSubmitErr(e instanceof Error ? e.message : "Failed to create goal");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />
      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />

        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">

          {/* Hero */}
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mb-10"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/25 bg-accent/8 mb-4">
              <Zap className="w-3.5 h-3.5 text-accent" />
              <span className="text-xs font-medium text-accent">GitHub Actions & Rulesets</span>
            </div>
            <h1 className="font-display font-bold text-white mb-3" style={{ fontSize: "clamp(1.8rem, 4vw, 2.6rem)" }}>
              Automate your CI/CD with{" "}
              <span className="text-gradient-blue">natural language</span>
            </h1>
            <p className="text-text-dim text-sm max-w-xl leading-relaxed">
              Inspect workflows and branch protection rules. Describe any change — agents will write the config, open a PR, and set the rules.
            </p>
          </motion.div>

          <div className="space-y-5">

            {/* Repo picker */}
            <SectionCard delay={0.05}>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                  <GitBranch className="w-3.5 h-3.5 text-accent" />
                </div>
                <h2 className="text-sm font-semibold text-white">Repository</h2>
              </div>
              <div className="flex gap-3">
                <input
                  value={repo}
                  onChange={e => setRepo(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && load()}
                  placeholder="owner/repo — e.g. MaskedBug601/Nothing"
                  className="flex-1 rounded-xl border border-white/10 bg-white/4 px-4 py-2.5 text-sm text-white placeholder-text-muted focus:outline-none focus:border-accent/40 focus:bg-white/6 transition-all font-mono"
                />
                <button
                  onClick={load}
                  disabled={loading || !repo.trim()}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-accent/15 text-accent border border-accent/25 hover:bg-accent/25 disabled:opacity-40 transition-all"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                  {loading ? "Loading…" : "Load"}
                </button>
              </div>
              {loadErr && <p className="mt-3 text-xs text-danger">{loadErr}</p>}
            </SectionCard>

            {/* Repo data */}
            {loadedRepo && workflows !== null && protection !== null && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="grid grid-cols-1 lg:grid-cols-2 gap-5"
              >
                {/* Workflows */}
                <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                      <Workflow className="w-3.5 h-3.5 text-accent" />
                    </div>
                    <h2 className="text-sm font-semibold text-white">
                      Workflows <span className="text-text-muted font-normal">({workflows.length})</span>
                    </h2>
                  </div>
                  {workflows.length === 0 ? (
                    <div className="text-center py-8 border border-dashed border-white/10 rounded-xl">
                      <Workflow className="w-8 h-8 mx-auto mb-2 text-text-muted opacity-40" />
                      <p className="text-xs text-text-muted">No workflows in .github/workflows/</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {workflows.map(wf => <WorkflowCard key={wf.path} wf={wf} />)}
                    </div>
                  )}
                </div>

                {/* Branch protection */}
                <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5 backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                      <Shield className="w-3.5 h-3.5 text-accent" />
                    </div>
                    <h2 className="text-sm font-semibold text-white">Branch Protection</h2>
                  </div>
                  <ProtectionCard data={protection} />
                </div>
              </motion.div>
            )}

            {/* Automate section */}
            <SectionCard delay={0.1}>
              <div className="flex items-center gap-2 mb-5">
                <div className="w-7 h-7 rounded-lg bg-purple/10 border border-purple/25 flex items-center justify-center">
                  <Play className="w-3.5 h-3.5 text-purple" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    Automate{loadedRepo ? <span className="text-text-muted font-normal"> — {loadedRepo}</span> : ""}
                  </h2>
                  {!loadedRepo && <p className="text-xs text-text-muted">Load a repository first, then describe what to change</p>}
                </div>
              </div>

              {/* Quick action chips */}
              <div className="flex flex-wrap gap-2 mb-4">
                {QUICK_ACTIONS.map(qa => (
                  <button
                    key={qa.label}
                    onClick={() => setInstruction(qa.instruction)}
                    className={`text-xs px-3 py-1.5 rounded-full border transition-all font-medium ${
                      instruction === qa.instruction
                        ? "border-accent/50 bg-accent/12 text-accent"
                        : "border-white/10 bg-white/[0.03] text-text-muted hover:text-white hover:border-white/20 hover:bg-white/6"
                    }`}
                  >
                    {qa.label}
                  </button>
                ))}
              </div>

              <textarea
                value={instruction}
                onChange={e => setInstruction(e.target.value)}
                placeholder={
                  loadedRepo
                    ? "Describe what you want — e.g. \"Add a CI workflow that runs pytest on every push\""
                    : "Load a repository above first, then describe what to automate…"
                }
                rows={4}
                className="w-full rounded-xl border border-white/10 bg-white/4 px-4 py-3 text-sm text-white placeholder-text-muted focus:outline-none focus:border-accent/40 focus:bg-white/6 transition-all resize-none mb-4"
              />

              <div className="flex items-center gap-3">
                <button
                  onClick={() => submit(instruction)}
                  disabled={submitting || !instruction.trim() || !loadedRepo}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold btn-neon text-white disabled:opacity-40 transition-all"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  {submitting ? "Delegating…" : "Delegate to Agent →"}
                </button>
                {submitErr && <p className="text-xs text-danger">{submitErr}</p>}
              </div>

              {submitted && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-4 flex items-center gap-3 rounded-xl border border-success/25 bg-success/8 px-4 py-3"
                >
                  <CheckCircle className="w-4 h-4 text-success shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-success font-semibold">Goal created — agents are on it</p>
                    <p className="text-xs text-text-muted font-mono truncate mt-0.5">{submitted}</p>
                  </div>
                  <button
                    onClick={() => nav(`/app/goals/${submitted}`)}
                    className="shrink-0 text-xs font-medium text-accent hover:text-white transition-colors flex items-center gap-1"
                  >
                    Watch live →
                  </button>
                </motion.div>
              )}
            </SectionCard>

            {/* Empty prompt */}
            {!loadedRepo && !loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.25 }}
                className="flex flex-col items-center justify-center py-16 text-center"
              >
                <div className="relative mb-4">
                  <div className="absolute inset-0 rounded-full bg-accent/15 blur-2xl scale-150" />
                  <div className="relative w-14 h-14 rounded-2xl bg-accent/8 border border-accent/15 flex items-center justify-center">
                    <GitBranch className="w-7 h-7 text-accent opacity-60" />
                  </div>
                </div>
                <p className="text-sm text-text-muted max-w-xs leading-relaxed">
                  Enter a repository above to inspect its CI/CD workflows and branch protection rules.
                </p>
              </motion.div>
            )}

          </div>
        </main>
      </div>
    </div>
  );
}
