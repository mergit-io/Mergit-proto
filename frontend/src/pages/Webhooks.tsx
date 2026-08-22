import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, Check } from "lucide-react";
import { Shell } from "../components/AppNav";
import { Micro, Notice, PageHead, Panel } from "../components/ui";

const api = {
  // Posts at /api/actions/simulate-issue, NOT at the webhook receiver.
  //
  // This used to hand-build a GitHub payload and POST it to /api/webhooks/github with no
  // signature, which worked only because that endpoint failed *open*. It now fails closed
  // — a forged issues.opened carries an attacker-controlled repository.full_name and would
  // point the agent pipeline at any repo — so simulation has its own route, and the server
  // builds the goal text with the same function the real webhook uses.
  async simulateIssue(repo: string, issueTitle: string, issueBody: string) {
    const res = await fetch("/api/actions/simulate-issue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo,
        title: issueTitle,
        body: issueBody,
        issue_number: Math.floor(Math.random() * 9000) + 1000,
      }),
    });
    return res.json();
  },
};

const PIPELINE = ["Issue opened", "Researcher reads code", "Coder writes fix", "Integrator opens PR", "Comment posted"];

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
      aria-label="Copy"
      className="p-2 border border-line text-dim hover:text-text hover:border-faint transition-colors shrink-0"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-mint" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 px-4 py-5 border-b border-line-soft last:border-0">
      <Micro className="shrink-0 text-faint">{n}</Micro>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text mb-1.5">{title}</p>
        <div className="text-sm text-dim leading-relaxed space-y-2">{children}</div>
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
    } catch (e: unknown) {
      setSimResult({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      setSimLoading(false);
    }
  };

  return (
    <Shell>
      <PageHead marker="AUTOMATION — ISSUE WEBHOOK" title="When an issue opens, agents fix it">
        Connect Mergit to GitHub. Agents read the code, write a fix, and open a pull request —
        no manual triage.
      </PageHead>

      <div className="flex flex-col gap-6">
        <Panel title="Webhook endpoint">
          <div className="flex items-center gap-2 px-4 py-3">
            <code className="font-mono text-xs bg-raise px-1.5 py-0.5 flex-1 break-all">{webhookUrl}</code>
            <CopyButton text={webhookUrl} />
          </div>
          <p className="px-4 pb-4 text-sm text-dim">
            Paste this into your GitHub repo → Settings → Webhooks → Add webhook. Set content type
            to <code className="font-mono text-xs bg-raise px-1.5 py-0.5">application/json</code>.
          </p>
        </Panel>

        <Panel title="Autonomous pipeline">
          <div className="flex flex-wrap divide-x divide-line">
            {PIPELINE.map((label) => (
              <span key={label} className="font-mono text-micro uppercase text-dim px-4 py-3">
                {label}
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Setup guide">
          <Step n="01" title="Expose Mergit with ngrok (local dev)">
            <p>Install ngrok and run:</p>
            <pre className="font-mono text-xs bg-raise border border-line p-4 overflow-x-auto">ngrok http 8000</pre>
            <p>
              Copy the <code className="font-mono text-xs bg-raise px-1.5 py-0.5">https://xxxx.ngrok-free.app</code>{" "}
              URL and use it as the base for the webhook URL above.
            </p>
          </Step>

          <Step n="02" title="Add the webhook to your GitHub repo">
            <p>
              Go to your repo → <span className="text-text">Settings → Webhooks → Add webhook</span>
            </p>
            <ul className="list-disc list-inside space-y-1">
              <li>
                Payload URL: your ngrok URL + <code className="font-mono text-xs bg-raise px-1.5 py-0.5">/api/webhooks/github</code>
              </li>
              <li>
                Content type: <code className="font-mono text-xs bg-raise px-1.5 py-0.5">application/json</code>
              </li>
              <li>
                Events: <span className="text-text">Issues</span> and <span className="text-text">Pull requests</span>
              </li>
            </ul>
          </Step>

          <Step n="03" title="Add a GitHub token">
            <p>
              Go to <span className="text-text">Models → API keys</span> and add a GitHub personal access
              token with <code className="font-mono text-xs bg-raise px-1.5 py-0.5">repo</code> scope.
            </p>
            <p className="text-amber">
              Without a token, Mergit can plan tasks but can't open pull requests or post comments.
            </p>
          </Step>

          <Step n="04" title="Open a GitHub issue — agents take it from here">
            <ul className="space-y-1.5">
              <li>Researcher reads the repo structure and relevant source files</li>
              <li>Coder writes and tests a fix based on the issue description</li>
              <li>Integrator opens a pull request with the fix</li>
              <li>A comment is posted on your issue with the PR link</li>
            </ul>
          </Step>
        </Panel>

        <Panel title="Simulate an issue" right={<Micro>No webhook required</Micro>}>
          <div className="p-4 flex flex-col gap-4">
            <div>
              <Micro className="block mb-1.5">Repository (owner/repo)</Micro>
              <input
                className="field font-mono"
                value={simRepo}
                onChange={(e) => setSimRepo(e.target.value)}
                placeholder="owner/repo"
              />
            </div>
            <div>
              <Micro className="block mb-1.5">Issue title</Micro>
              <input className="field" value={simTitle} onChange={(e) => setSimTitle(e.target.value)} />
            </div>
            <div>
              <Micro className="block mb-1.5">Issue body</Micro>
              <textarea
                className="field resize-y"
                rows={9}
                value={simBody}
                onChange={(e) => setSimBody(e.target.value)}
              />
            </div>

            <button onClick={handleSimulate} disabled={simLoading} className="btn-primary w-full">
              {simLoading ? "Simulating…" : "Simulate issue"}
            </button>

            {simResult && (
              <Notice tone={simResult.goal_id ? "done" : "fail"}>
                {simResult.goal_id ? (
                  <>
                    Simulated — agents are planning the fix.{" "}
                    <button
                      onClick={() => nav(`/app/goals/${simResult.goal_id}`)}
                      className="underline hover:no-underline"
                    >
                      Watch live →
                    </button>
                  </>
                ) : (
                  <>Could not simulate the issue: {simResult.error || JSON.stringify(simResult)}</>
                )}
              </Notice>
            )}
          </div>
        </Panel>
      </div>
    </Shell>
  );
}
