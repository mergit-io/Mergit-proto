import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
// lucide-react dropped its brand icons, so these are the generic equivalents already
// used elsewhere in the app rather than inlined SVG logos.
import { AlertTriangle, Check, GitBranch, Hash, Loader2, Plug, Trash2 } from "lucide-react";
import { AppBackground } from "../components/AppBackground";
import { AppNav } from "../components/AppNav";
import { getCsrfToken } from "../lib/auth";

/**
 * What Mergit is allowed to do as you, and how to take it back.
 *
 * Two things this page deliberately does NOT do:
 *
 *  - **It never shows a token, not even masked.** `Models.tsx` masks Mergit's own provider
 *    keys, which is right there — the operator pasted those and may need to confirm which
 *    one is set. A credential Mergit holds *on your behalf* is different: there is nothing
 *    for you to copy, so showing `ghu_1234…abcd` would only suggest otherwise.
 *  - **It does not claim disconnecting revokes everything.** For GitHub the installation
 *    itself lives on GitHub and only you can remove it, so the card says so and links there
 *    rather than implying a clean break we cannot deliver.
 */

interface Connection {
  id: string;
  provider: string;
  account: string;
  display_name: string;
  scopes: string[];
  status: string;
  installation_id: number | null;
  account_type: string;
  connected_at: number;
}

interface ConnectionsPayload {
  connections: Connection[];
  github_repositories: string[];
  available: Record<string, boolean>;
}

const PROVIDERS = [
  {
    key: "github",
    label: "GitHub",
    Icon: GitBranch,
    blurb: "Open pull requests, review and merge them, and manage issues on repositories you choose.",
    // Plain English, not scope strings. "contents:write" tells a user nothing about what
    // will happen to their repository.
    permissions: [
      "Read the repositories you select",
      "Commit to a branch and open pull requests",
      "Comment on, label and close issues",
      "Merge a pull request — only after you approve it",
    ],
  },
  {
    key: "slack",
    label: "Slack",
    Icon: Hash,
    blurb: "Build, install and test a bot in your workspace, and post as it.",
    permissions: [
      "Read the channels you invite the bot to",
      "Post messages as the bot",
      "Create a temporary channel to test a new bot, then archive it",
    ],
  },
] as const;

export function Connections() {
  const [data, setData] = useState<ConnectionsPayload | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/connections", { credentials: "same-origin" });
      if (res.ok) setData(await res.json());
    } catch {
      setError("Could not load your connections.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // The OAuth callback redirects back here with ?github=connected|failed|pending_org_approval.
  const banner = PROVIDERS.map((p) => [p.key, params.get(p.key)] as const).find(([, v]) => v);

  const connect = async (provider: string) => {
    setBusy(provider);
    setError("");
    try {
      const res = await fetch(`/api/connections/${provider}/start`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-Mergit-CSRF": getCsrfToken() },
      });
      if (!res.ok) {
        setError((await res.json()).detail ?? "Could not start the connection.");
        setBusy(null);
        return;
      }
      // A full-page navigation, not fetch: the provider's consent screen is a redirect.
      window.location.href = (await res.json()).url;
    } catch {
      setError("Could not reach the server.");
      setBusy(null);
    }
  };

  const disconnect = async (provider: string) => {
    setBusy(provider);
    try {
      await fetch(`/api/connections/${provider}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "X-Mergit-CSRF": getCsrfToken() },
      });
      await load();
    } finally {
      setBusy(null);
    }
  };

  const connectionFor = (key: string) => data?.connections.find((c) => c.provider === key);

  return (
    <div className="relative min-h-screen" style={{ background: "#FFFDFB" }}>
      <AppBackground />
      <div className="relative z-10 flex flex-col min-h-screen">
        <AppNav />
        <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">
          <header className="mb-8">
            <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
              <Plug className="w-5 h-5" /> Connections
            </h1>
            <p className="mt-2 text-sm text-ink/50 max-w-2xl">
              Signing in with Google tells Mergit who you are. It does not give Mergit any
              access to GitHub or Slack — each one is its own permission, granted here, and
              revocable here.
            </p>
          </header>

          {banner && <Banner provider={banner[0]} status={banner[1]!} onDismiss={() => setParams({})} />}
          {error && (
            <div className="mb-6 rounded-xl border border-red-400/25 bg-red-400/10 px-4 py-3 text-sm text-red-200/90">
              {error}
            </div>
          )}

          <div className="space-y-4">
            {PROVIDERS.map((p) => (
              <ProviderCard
                key={p.key}
                meta={p}
                connection={connectionFor(p.key)}
                repos={p.key === "github" ? data?.github_repositories ?? [] : []}
                available={data?.available?.[p.key] ?? false}
                busy={busy === p.key}
                onConnect={() => connect(p.key)}
                onDisconnect={() => disconnect(p.key)}
              />
            ))}
          </div>

          <p className="mt-8 text-xs text-ink/30 leading-relaxed">
            Mergit records every use of these connections — which agent, which action, and on
            what — on the{" "}
            <a href="/app/audit" className="text-ink/50 underline underline-offset-2">
              activity page
            </a>
            .
          </p>
        </main>
      </div>
    </div>
  );
}

function Banner({ provider, status, onDismiss }: {
  provider: string; status: string; onDismiss: () => void;
}) {
  const tone =
    status === "connected" ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200/90"
    : status === "pending_org_approval" ? "border-amber-400/25 bg-amber-400/10 text-amber-200/90"
    : "border-red-400/25 bg-red-400/10 text-red-200/90";

  const text =
    status === "connected" ? `${provider} connected. Any paused goals have resumed.`
    // The state every design forgets. A user who followed instructions and hit an org
    // approval wall otherwise lands on a page that looks like it silently failed.
    : status === "pending_org_approval"
      ? "Your organisation's owner needs to approve Mergit before it can act on those repositories. They will have received a request — this page will update once they approve."
      : `That ${provider} connection did not complete. Nothing was saved — you can try again.`;

  return (
    <div className={`mb-6 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${tone}`}>
      <span className="flex-1">{text}</span>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100">×</button>
    </div>
  );
}

function ProviderCard({ meta, connection, repos, available, busy, onConnect, onDisconnect }: {
  meta: (typeof PROVIDERS)[number];
  connection?: Connection;
  repos: string[];
  available: boolean;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const { Icon } = meta;
  const connected = connection?.status === "active";
  const needsReauth = connection?.status === "needs_reauth";

  return (
    <section className="rounded-2xl border border-ink/[0.09] bg-white/[0.03] p-5">
      <div className="flex items-start gap-4">
        <Icon className="w-5 h-5 mt-0.5 text-ink/70 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-ink">{meta.label}</h2>
            {connected && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/15 px-2 py-0.5 text-[11px] text-emerald-300">
                <Check className="w-3 h-3" /> Connected
              </span>
            )}
            {needsReauth && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2 py-0.5 text-[11px] text-amber-300">
                <AlertTriangle className="w-3 h-3" /> Reconnect needed
              </span>
            )}
          </div>

          <p className="mt-1 text-sm text-ink/50">{meta.blurb}</p>

          {connected ? (
            <div className="mt-3 space-y-2 text-xs text-ink/45">
              <p>
                Connected as <span className="text-ink/75">{connection!.account}</span>
                {connection!.account_type === "Organization" && " (organisation)"}
              </p>
              {meta.key === "github" && (
                <div>
                  <p className="text-ink/60">Mergit can act on:</p>
                  {repos.length ? (
                    <ul className="mt-1 flex flex-wrap gap-1.5">
                      {repos.map((r) => (
                        <li key={r} className="rounded-md bg-white/[0.06] px-2 py-0.5 font-mono text-[11px] text-ink/70">
                          {r}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-ink/40">
                      Every repository on this account. Narrow it on GitHub if you would rather
                      pick specific ones.
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <ul className="mt-3 space-y-1 text-xs text-ink/45">
              {meta.permissions.map((p) => (
                <li key={p} className="flex gap-2">
                  <span className="text-ink/25">•</span> {p}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="shrink-0">
          {!available ? (
            <span className="text-xs text-ink/30">Not configured</span>
          ) : connected ? (
            <button
              onClick={onDisconnect}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink/[0.09] px-3 py-1.5
                         text-xs text-ink/60 transition-all hover:border-red-400/30 hover:text-red-300"
            >
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              Disconnect
            </button>
          ) : (
            <button
              onClick={onConnect}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5
                         text-xs font-medium text-black transition-all hover:bg-ink/[0.04] disabled:opacity-50"
            >
              {busy && <Loader2 className="w-3 h-3 animate-spin" />}
              {needsReauth ? "Reconnect" : "Connect"}
            </button>
          )}
        </div>
      </div>

      {connected && meta.key === "github" && (
        <p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] text-ink/30">
          Disconnecting removes Mergit's stored access. The app installation itself lives on
          GitHub — remove it at{" "}
          <a
            href="https://github.com/settings/installations"
            target="_blank"
            rel="noreferrer"
            className="text-ink/50 underline underline-offset-2"
          >
            github.com/settings/installations
          </a>{" "}
          to revoke it fully.
        </p>
      )}
    </section>
  );
}
