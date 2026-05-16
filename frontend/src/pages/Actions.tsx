import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  GitBranch, Shield, Play, RefreshCw, ChevronDown, ChevronRight,
  CheckCircle, XCircle, Loader2, Workflow, Lock, Unlock, ArrowRight
} from "lucide-react";
import { AppNav } from "../components/AppNav";

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
  { label: "Add CI workflow (pytest)", instruction: "Add a GitHub Actions CI workflow that runs pytest on every push and pull request to the main branch." },
  { label: "Add CI workflow (npm test)", instruction: "Add a GitHub Actions CI workflow that runs npm test on every push and pull request." },
  { label: "Add lint workflow", instruction: "Add a GitHub Actions workflow that runs ruff and mypy on every push for code quality." },
  { label: "Require PR reviews", instruction: "Enable branch protection on the default branch: require at least 1 approving review before merging and dismiss stale reviews." },
  { label: "Enforce status checks", instruction: "Enable branch protection: require status checks to pass before merging, with strict mode enabled." },
  { label: "Add release workflow", instruction: "Add a GitHub Actions release workflow that creates a GitHub Release and uploads build artifacts when a tag is pushed." },
  { label: "Add dependabot config", instruction: "Add a Dependabot configuration file to auto-update Python pip and GitHub Actions dependencies weekly." },
];

function WorkflowCard({ wf }: { wf: { name: string; path: string; content: string } }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-white/8 bg-white/3 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/4 transition-colors"
      >
        <Workflow className="w-4 h-4 text-accent shrink-0" />
        <span className="flex-1 text-sm font-medium text-white truncate">{wf.name}</span>
        <span className="text-xs text-text-muted font-mono">{wf.path}</span>
        {open ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
      </button>
      {open && (
        <div className="border-t border-white/6 p-4">
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
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs text-white font-medium">{value}</span>
    </div>
  );

  const Bool = ({ v }: { v: boolean }) => v
    ? <span className="flex items-center gap-1 text-emerald-400"><CheckCircle className="w-3 h-3" /> Yes</span>
    : <span className="flex items-center gap-1 text-text-muted"><XCircle className="w-3 h-3" /> No</span>;

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-4 space-y-1">
      <div className="flex items-center gap-2 mb-3">
        {data.protected
          ? <Lock className="w-4 h-4 text-emerald-400" />
          : <Unlock className="w-4 h-4 text-text-muted" />}
        <span className="text-sm font-semibold text-white">{data.branch}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded border ${data.protected ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/8" : "text-text-muted border-white/10 bg-white/4"}`}>
          {data.protected ? "Protected" : "Unprotected"}
        </span>
      </div>
      {data.protected && (
        <>
          <Row label="Enforce admins" value={<Bool v={!!rules.enforce_admins} />} />
          <Row label="Required status checks" value={
            rules.required_status_checks
              ? <span className="text-emerald-400">{rules.required_status_checks.contexts.length} context(s)</span>
              : <Bool v={false} />
          } />
          <Row label="Required PR reviews" value={
            rules.required_pull_request_reviews
              ? <span className="text-emerald-400">{rules.required_pull_request_reviews.required_approving_review_count} reviewer(s)</span>
              : <Bool v={false} />
          } />
          {rules.required_pull_request_reviews && (
            <>
              <Row label="Dismiss stale reviews" value={<Bool v={rules.required_pull_request_reviews.dismiss_stale_reviews} />} />
              <Row label="Require code owner reviews" value={<Bool v={rules.required_pull_request_reviews.require_code_owner_reviews} />} />
            </>
          )}
        </>
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
    try {
      const [wf, prot] = await Promise.all([
        fetchWorkflows(repo.trim()),
        fetchProtection(repo.trim()),
      ]);
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
    <div className="min-h-screen bg-background text-white">
      <AppNav />
      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center">
              <GitBranch className="w-4.5 h-4.5 text-accent" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">GitHub Actions & Rulesets</h1>
              <p className="text-xs text-text-muted">Inspect workflows, branch protection, and automate changes via natural language</p>
            </div>
          </div>
        </motion.div>

        {/* Repo picker */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className="rounded-2xl border border-white/8 bg-white/3 p-5 mb-6"
        >
          <p className="text-xs text-text-muted uppercase tracking-widest font-semibold mb-3">Repository</p>
          <div className="flex gap-3">
            <input
              value={repo}
              onChange={e => setRepo(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              placeholder="owner/repo (e.g. MaskedBug601/Nothing)"
              className="flex-1 bg-white/4 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-text-muted outline-none focus:border-accent/50 transition-colors font-mono"
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
          {loadErr && <p className="mt-2 text-xs text-danger">{loadErr}</p>}
        </motion.div>

        {/* Repo data */}
        {loadedRepo && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Workflows */}
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              <div className="flex items-center gap-2 mb-3">
                <Workflow className="w-4 h-4 text-accent" />
                <p className="text-xs text-text-muted uppercase tracking-widest font-semibold">
                  Workflows ({workflows?.length ?? 0})
                </p>
              </div>
              {workflows && workflows.length === 0 && (
                <p className="text-xs text-text-muted py-6 text-center border border-white/6 rounded-xl">
                  No workflows found in .github/workflows/
                </p>
              )}
              <div className="space-y-2">
                {workflows?.map(wf => <WorkflowCard key={wf.path} wf={wf} />)}
              </div>
            </motion.div>

            {/* Branch protection */}
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
              <div className="flex items-center gap-2 mb-3">
                <Shield className="w-4 h-4 text-accent" />
                <p className="text-xs text-text-muted uppercase tracking-widest font-semibold">Branch Protection</p>
              </div>
              {protection && <ProtectionCard data={protection} />}
            </motion.div>
          </div>
        )}

        {/* Action section — always visible */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="rounded-2xl border border-white/8 bg-white/3 p-5"
        >
          <p className="text-xs text-text-muted uppercase tracking-widest font-semibold mb-1">
            Automate{loadedRepo ? ` — ${loadedRepo}` : ""}
          </p>
          {!loadedRepo && (
            <p className="text-xs text-text-muted mb-4">Load a repository above first, then describe what to change.</p>
          )}

          {/* Quick actions */}
          <div className="flex flex-wrap gap-2 mb-4 mt-3">
            {QUICK_ACTIONS.map(qa => (
              <button
                key={qa.label}
                onClick={() => setInstruction(qa.instruction)}
                className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 bg-white/4 text-text-muted hover:text-white hover:border-white/20 transition-all"
              >
                {qa.label}
              </button>
            ))}
          </div>

          {/* Instruction input */}
          <textarea
            value={instruction}
            onChange={e => setInstruction(e.target.value)}
            placeholder={loadedRepo
              ? "Describe what you want to change — e.g. 'Add a CI workflow that runs pytest on push'"
              : "Load a repository first, then describe what to automate…"}
            rows={3}
            className="w-full bg-white/4 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder:text-text-muted outline-none focus:border-accent/40 transition-colors resize-none mb-3"
          />

          <div className="flex items-center gap-3">
            <button
              onClick={() => submit(instruction)}
              disabled={submitting || !instruction.trim() || !loadedRepo}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-accent text-white hover:bg-accent/90 disabled:opacity-40 transition-all"
            >
              {submitting
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Play className="w-4 h-4" />}
              {submitting ? "Delegating…" : "Delegate to Agent"}
            </button>
            {submitErr && <p className="text-xs text-danger">{submitErr}</p>}
          </div>

          {submitted && (
            <motion.div
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              className="mt-4 flex items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/8 px-4 py-3"
            >
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-emerald-300 font-semibold">Goal created — agent is working on it</p>
                <p className="text-xs text-text-muted font-mono truncate mt-0.5">{submitted}</p>
              </div>
              <button
                onClick={() => nav(`/app/goals/${submitted}`)}
                className="flex items-center gap-1 text-xs text-accent hover:text-accent/80 transition-colors shrink-0 font-medium"
              >
                View <ArrowRight className="w-3 h-3" />
              </button>
            </motion.div>
          )}
        </motion.div>

        {/* Empty state */}
        {!loadedRepo && !loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
            className="text-center py-20 text-text-muted"
          >
            <GitBranch className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Enter a repo above to inspect its workflows and branch protection</p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
