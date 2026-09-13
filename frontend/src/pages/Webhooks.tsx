import { useState } from "react";
import { motion } from "framer-motion";
import { Copy, Check, Zap, GitBranch, Terminal, AlertCircle, ArrowRight, ExternalLink } from "lucide-react";
import { AppNav } from "../components/AppNav";
import { useNavigate } from "react-router-dom";

const api = {
  async simulateIssue(repo: string, issueTitle: string, issueBody: string) {
    const payload = {
      action: "opened",
      issue: {
        number: Math.floor(Math.random() * 9000) + 1000,
        title: issueTitle,
        body: issueBody,
        html_url: `https://github.com/${repo}/issues/1`,
        user: { login: "demo-user", type: "User" },
        labels: [],
      },
      repository: {
        full_name: repo,
        default_branch: "main",
      },
    };
    const res = await fetch("/api/webhooks/github", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Github-Event": "issues" },
      body: JSON.stringify(payload),
    });
    return res.json();
  },
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="ml-2 p-1 rounded text-text-muted hover:text-white transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative bg-white/3 rounded-lg border border-white/8 p-4 mt-2">
      <pre className="text-xs font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap">{code}</pre>
      <div className="absolute top-2 right-2">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-xs font-bold text-blue-400 mt-0.5">
        {n}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white mb-1">{title}</p>
        <div className="text-xs text-text-muted leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

export function Webhooks() {
  const nav = useNavigate();
  const webhookUrl = `${window.location.origin}/api/webhooks/github`;
  const [simRepo, setSimRepo] = useState("owner/repo");
  const [simTitle, setSimTitle] = useState("Bug: function returns incorrect value for edge case");
  const [simBody, setSimBody] = useState(
    "The `calculate` function in `src/utils.py` returns `None` when the input is 0 instead of returning 0. This causes downstream processing to crash.\n\nSteps to reproduce:\n1. Call `calculate(0)`\n2. Observe `None` returned\n\nExpected: `0`"
  );
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<{ goal_id?: string; error?: string } | null>(null);

  const handleSimulate = async () => {
    setSimLoading(true);
    setSimResult(null);
    try {
      const result = await api.simulateIssue(simRepo, simTitle, simBody);
      setSimResult(result);
    } catch (e: any) {
      setSimResult({ error: e.message });
    } finally {
      setSimLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <AppNav />
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
              <Zap className="w-4 h-4 text-purple-400" />
            </div>
            <h1 className="text-xl font-display font-bold text-white">GitHub Automation</h1>
          </div>
          <p className="text-sm text-text-muted">
            Connect omniBox to GitHub. When an issue is opened, omniBox reads the code, writes a fix, and creates a PR — automatically.
          </p>
        </motion.div>

        {/* Webhook URL */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="card p-4 mb-6"
        >
          <div className="flex items-center gap-2 mb-3">
            <GitBranch className="w-4 h-4 text-white" />
            <h2 className="text-sm font-semibold text-white">Webhook URL</h2>
          </div>
          <div className="flex items-center gap-2 bg-white/3 rounded-lg border border-white/8 px-3 py-2.5">
            <code className="text-xs font-mono text-blue-300 flex-1 break-all">{webhookUrl}</code>
            <CopyButton text={webhookUrl} />
          </div>
          <p className="text-xs text-text-muted mt-2">
            Paste this into your GitHub repo → Settings → Webhooks → Add webhook
          </p>
        </motion.div>

        {/* Setup Guide */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="card p-5 mb-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="w-4 h-4 text-white" />
            <h2 className="text-sm font-semibold text-white">Setup Guide</h2>
          </div>
          <div className="space-y-5">
            <Step n={1} title="Expose omniBox via ngrok (local dev)">
              <p className="mb-1">Install ngrok, then run:</p>
              <CodeBlock code="ngrok http 8000" />
              <p className="mt-2">Copy the <span className="text-white font-mono">https://xxxx.ngrok-free.app</span> URL and replace <code className="text-white">localhost:8000</code> above.</p>
            </Step>

            <Step n={2} title="Add the webhook to your GitHub repo">
              <p>Go to your repo → <strong className="text-white">Settings → Webhooks → Add webhook</strong></p>
              <ul className="mt-2 space-y-1 list-disc list-inside">
                <li>Payload URL: <em className="text-white">(your URL from above)</em></li>
                <li>Content type: <code className="text-white">application/json</code></li>
                <li>Events: <strong className="text-white">Issues</strong> and <strong className="text-white">Pull requests</strong></li>
              </ul>
            </Step>

            <Step n={3} title="Configure GITHUB_TOKEN">
              <p>
                Go to <strong className="text-white">Models → API Keys</strong> and paste a GitHub personal access token
                with <code className="text-white">repo</code> scope.
              </p>
              <div className="mt-2 p-2 rounded bg-amber-500/10 border border-amber-500/20 flex items-start gap-2">
                <AlertCircle className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                <span className="text-amber-300">Without a token, omniBox can plan tasks but can't create PRs or post comments.</span>
              </div>
            </Step>

            <Step n={4} title="Open a GitHub issue">
              <p>Create an issue on your repo describing a bug. omniBox will automatically:</p>
              <div className="mt-2 space-y-1">
                {[
                  "Read the relevant source files",
                  "Write a code fix using the coder agent",
                  "Create a pull request with the fix",
                  "Post a comment on your issue with the PR link",
                ].map((step, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <ArrowRight className="w-3 h-3 text-blue-400 flex-shrink-0" />
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </Step>
          </div>
        </motion.div>

        {/* Demo Simulator */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="card p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-4 h-4 text-green-400" />
            <h2 className="text-sm font-semibold text-white">Simulate GitHub Issue</h2>
            <span className="text-xs text-text-muted ml-1">— test without a real webhook</span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-text-muted mb-1 block">Repository (owner/repo)</label>
              <input
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-text-muted focus:outline-none focus:border-blue-500/50 transition-colors"
                value={simRepo}
                onChange={(e) => setSimRepo(e.target.value)}
                placeholder="owner/repo"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Issue title</label>
              <input
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-text-muted focus:outline-none focus:border-blue-500/50 transition-colors"
                value={simTitle}
                onChange={(e) => setSimTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Issue body</label>
              <textarea
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-text-muted focus:outline-none focus:border-blue-500/50 transition-colors resize-none"
                rows={4}
                value={simBody}
                onChange={(e) => setSimBody(e.target.value)}
              />
            </div>

            <button
              onClick={handleSimulate}
              disabled={simLoading}
              className="w-full py-2.5 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white text-sm font-medium transition-all disabled:opacity-50"
            >
              {simLoading ? "Creating goal…" : "Simulate Issue Opened →"}
            </button>

            {simResult && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className={`p-3 rounded-lg border text-xs ${
                  simResult.goal_id
                    ? "bg-green-500/10 border-green-500/20 text-green-300"
                    : "bg-red-500/10 border-red-500/20 text-red-300"
                }`}
              >
                {simResult.goal_id ? (
                  <div className="flex items-center justify-between">
                    <span>
                      Goal created — agents are planning the fix
                    </span>
                    <button
                      onClick={() => nav(`/app/goals/${simResult.goal_id}`)}
                      className="flex items-center gap-1 text-green-200 hover:text-white underline ml-3"
                    >
                      Watch live <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <span>Error: {simResult.error || JSON.stringify(simResult)}</span>
                )}
              </motion.div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
