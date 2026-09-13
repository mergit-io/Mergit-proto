import { useState } from "react";
import { motion } from "framer-motion";
import { Copy, Check, Zap, GitBranch, Terminal, AlertCircle, ArrowRight, ExternalLink } from "lucide-react";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
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
      className="p-1.5 rounded-lg text-text-muted hover:text-white hover:bg-white/8 transition-all"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 rounded bg-white/8 border border-white/10 text-xs font-mono text-accent-2">
      {children}
    </code>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative rounded-xl border border-white/8 bg-black/40 p-4 mt-2 group">
      <pre className="text-xs font-mono text-text-dim overflow-x-auto whitespace-pre-wrap pr-8">{code}</pre>
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center text-xs font-bold text-accent mt-0.5">
        {n}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white mb-1.5">{title}</p>
        <div className="text-xs text-text-muted leading-relaxed space-y-1">{children}</div>
      </div>
    </div>
  );
}

function SectionCard({ delay = 0, children }: { delay?: number; children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-white/8 bg-white/[0.02] p-6 backdrop-blur-sm"
    >
      {children}
    </motion.div>
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
    } catch (e: unknown) {
      setSimResult({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      setSimLoading(false);
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
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-purple/25 bg-purple/8 mb-4">
              <Zap className="w-3.5 h-3.5 text-purple" />
              <span className="text-xs font-medium text-purple">GitHub Automation</span>
            </div>
            <h1 className="font-display font-bold text-white mb-3" style={{ fontSize: "clamp(1.8rem, 4vw, 2.6rem)" }}>
              Auto-fix issues with{" "}
              <span className="text-gradient-blue">zero intervention</span>
            </h1>
            <p className="text-text-dim text-sm max-w-xl leading-relaxed">
              Connect omniBox to GitHub. When an issue is opened, agents read the code, write a fix, and open a PR — fully autonomously.
            </p>
          </motion.div>

          <div className="space-y-5">

            {/* Webhook URL */}
            <SectionCard delay={0.05}>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                  <GitBranch className="w-3.5 h-3.5 text-accent" />
                </div>
                <h2 className="text-sm font-semibold text-white">Webhook Endpoint</h2>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-4 py-3">
                <code className="text-xs font-mono text-accent flex-1 break-all">{webhookUrl}</code>
                <CopyButton text={webhookUrl} />
              </div>
              <p className="text-xs text-text-muted mt-3">
                Paste this into your GitHub repo → Settings → Webhooks → Add webhook. Set content type to <InlineCode>application/json</InlineCode>.
              </p>
            </SectionCard>

            {/* Pipeline visual */}
            <SectionCard delay={0.1}>
              <h2 className="text-sm font-semibold text-white mb-4">Autonomous Pipeline</h2>
              <div className="flex items-center gap-2 flex-wrap">
                {[
                  { label: "Issue opened", color: "border-purple/40 bg-purple/8 text-purple" },
                  { label: "Researcher reads code", color: "border-accent/40 bg-accent/8 text-accent" },
                  { label: "Coder writes fix", color: "border-cyan/40 bg-cyan/8 text-cyan" },
                  { label: "Integrator opens PR", color: "border-success/40 bg-success/8 text-success" },
                  { label: "Comment posted", color: "border-warning/40 bg-warning/8 text-warning" },
                ].map((step, i, arr) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className={`px-3 py-1.5 rounded-full border text-xs font-medium ${step.color}`}>
                      {step.label}
                    </span>
                    {i < arr.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />}
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Setup Guide */}
            <SectionCard delay={0.15}>
              <div className="flex items-center gap-2 mb-5">
                <div className="w-7 h-7 rounded-lg bg-white/6 border border-white/10 flex items-center justify-center">
                  <Terminal className="w-3.5 h-3.5 text-text-dim" />
                </div>
                <h2 className="text-sm font-semibold text-white">Setup Guide</h2>
              </div>
              <div className="space-y-6">
                <Step n={1} title="Expose omniBox via ngrok (local dev)">
                  <p className="mb-1">Install ngrok and run:</p>
                  <CodeBlock code="ngrok http 8000" />
                  <p className="mt-2">Copy the <span className="text-white font-mono">https://xxxx.ngrok-free.app</span> URL — use it as the base for the webhook URL above.</p>
                </Step>

                <div className="border-t border-white/6" />

                <Step n={2} title="Add the webhook to your GitHub repo">
                  <p>Go to your repo → <strong className="text-white">Settings → Webhooks → Add webhook</strong></p>
                  <ul className="mt-2 space-y-1 list-disc list-inside">
                    <li>Payload URL: <em className="text-white">your ngrok URL + /api/webhooks/github</em></li>
                    <li>Content type: <InlineCode>application/json</InlineCode></li>
                    <li>Events: <strong className="text-white">Issues</strong> and <strong className="text-white">Pull requests</strong></li>
                  </ul>
                </Step>

                <div className="border-t border-white/6" />

                <Step n={3} title="Configure GITHUB_TOKEN">
                  <p>
                    Go to <strong className="text-white">Models → API Keys</strong> and paste a GitHub personal access token
                    with <InlineCode>repo</InlineCode> scope.
                  </p>
                  <div className="mt-2 p-3 rounded-xl bg-warning/8 border border-warning/20 flex items-start gap-2">
                    <AlertCircle className="w-3.5 h-3.5 text-warning mt-0.5 flex-shrink-0" />
                    <span className="text-warning/90">Without a token, omniBox can plan tasks but can't create PRs or post comments.</span>
                  </div>
                </Step>

                <div className="border-t border-white/6" />

                <Step n={4} title="Open a GitHub issue — agents take it from here">
                  <div className="mt-1 space-y-1.5">
                    {[
                      "Researcher reads the repo structure and relevant source files",
                      "Coder writes and tests a fix based on the issue description",
                      "Integrator opens a pull request with the fix",
                      "A comment is posted on your issue with the PR link",
                    ].map((s, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                </Step>
              </div>
            </SectionCard>

            {/* Simulator */}
            <SectionCard delay={0.2}>
              <div className="flex items-center gap-2 mb-5">
                <div className="w-7 h-7 rounded-lg bg-success/10 border border-success/20 flex items-center justify-center">
                  <Zap className="w-3.5 h-3.5 text-success" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Simulate GitHub Issue</h2>
                  <p className="text-xs text-text-muted">Test without a real webhook</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-text-muted mb-1.5 block">Repository <span className="text-text-muted font-normal">(owner/repo)</span></label>
                  <input
                    className="w-full rounded-xl border border-white/10 bg-white/4 px-3 py-2.5 text-sm text-white placeholder-text-muted focus:outline-none focus:border-accent/40 focus:bg-white/6 transition-all"
                    value={simRepo}
                    onChange={(e) => setSimRepo(e.target.value)}
                    placeholder="owner/repo"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-text-muted mb-1.5 block">Issue title</label>
                  <input
                    className="w-full rounded-xl border border-white/10 bg-white/4 px-3 py-2.5 text-sm text-white placeholder-text-muted focus:outline-none focus:border-accent/40 focus:bg-white/6 transition-all"
                    value={simTitle}
                    onChange={(e) => setSimTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-text-muted mb-1.5 block">Issue body</label>
                  <textarea
                    className="w-full rounded-xl border border-white/10 bg-white/4 px-3 py-2.5 text-sm text-white placeholder-text-muted focus:outline-none focus:border-accent/40 focus:bg-white/6 transition-all resize-none"
                    rows={4}
                    value={simBody}
                    onChange={(e) => setSimBody(e.target.value)}
                  />
                </div>

                <button
                  onClick={handleSimulate}
                  disabled={simLoading}
                  className="w-full py-2.5 rounded-xl font-medium text-sm text-white transition-all disabled:opacity-50 btn-neon"
                >
                  {simLoading ? "Creating goal…" : "Simulate Issue Opened →"}
                </button>

                {simResult && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`p-3.5 rounded-xl border text-xs ${
                      simResult.goal_id
                        ? "bg-success/8 border-success/20 text-success"
                        : "bg-danger/8 border-danger/20 text-red-300"
                    }`}
                  >
                    {simResult.goal_id ? (
                      <div className="flex items-center justify-between gap-3">
                        <span>Goal created — agents are planning the fix</span>
                        <button
                          onClick={() => nav(`/app/goals/${simResult.goal_id}`)}
                          className="flex items-center gap-1 text-white underline underline-offset-2 hover:no-underline shrink-0"
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
            </SectionCard>

          </div>
        </main>
      </div>
    </div>
  );
}
