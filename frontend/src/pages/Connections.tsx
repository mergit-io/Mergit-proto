import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
// lucide-react dropped its brand icons, so these are the generic equivalents already
// used elsewhere in the app rather than inlined SVG logos.
import { GitBranch, Hash } from "lucide-react";
import { Shell } from "../components/AppNav";
import { Micro, Notice, PageHead, Panel, Status } from "../components/ui";
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
    <Shell>
      <PageHead marker="ACCESS — CONNECTIONS" title="Connections">
        Signing in with Google tells Mergit who you are. It does not give Mergit any access to
        GitHub or Slack — each one is its own permission, granted here, and revocable here.
      </PageHead>

      {banner && (
        <div className="mb-6">
          <ConnectionBanner provider={banner[0]} status={banner[1]!} onDismiss={() => setParams({})} />
        </div>
      )}
      {error && (
        <div className="mb-6">
          <Notice onDismiss={() => setError("")}>{error}</Notice>
        </div>
      )}

      <div className="space-y-6">
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

      {/* This linked to /app/audit, which is not a route and never was — the link rendered
          a blank page, and the sentence promised somewhere to read the log that does not
          exist. The recording is real (`GET /api/connections/audit`); the page is not, so
          the copy now claims only the part that is true. */}
      <p className="mt-8 text-xs text-dim leading-relaxed">
        Mergit records every use of these connections — which agent, which action, and on what.
      </p>
    </Shell>
  );
}

function ConnectionBanner({
  provider,
  status,
  onDismiss,
}: {
  provider: string;
  status: string;
  onDismiss: () => void;
}) {
  const tone: "done" | "wait" | "fail" =
    status === "connected" ? "done" : status === "pending_org_approval" ? "wait" : "fail";

  const text =
    status === "connected" ? (
      `${provider} connected. Any paused goals have resumed.`
    ) : status === "pending_org_approval" ? (
      // The state every design forgets. A user who followed instructions and hit an org
      // approval wall otherwise lands on a page that looks like it silently failed.
      "Your organisation's owner needs to approve Mergit before it can act on those repositories. They will have received a request — this page will update once they approve."
    ) : (
      `That ${provider} connection did not complete. Nothing was saved — you can try again.`
    );

  return (
    <Notice tone={tone} onDismiss={onDismiss}>
      {text}
    </Notice>
  );
}

function ProviderCard({
  meta,
  connection,
  repos,
  available,
  busy,
  onConnect,
  onDisconnect,
}: {
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
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Icon className="w-3.5 h-3.5 text-dim" />
          {meta.label}
        </span>
      }
      right={
        connected ? (
          <Status status="DONE" label="Connected" />
        ) : needsReauth ? (
          <Status status="PENDING" label="Reconnect needed" />
        ) : undefined
      }
      bodyClass="p-5"
    >
      <div className="flex items-start gap-6">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-dim leading-relaxed">{meta.blurb}</p>

          {connected ? (
            <div className="mt-4 space-y-2 text-sm text-dim">
              <p>
                Connected as <span className="text-text">{connection!.account}</span>
                {connection!.account_type === "Organization" && " (organisation)"}
              </p>
              {meta.key === "github" && (
                <div>
                  <Micro>Mergit can act on</Micro>
                  {repos.length ? (
                    <ul className="mt-2 flex flex-wrap gap-1.5">
                      {repos.map((r) => (
                        <li key={r} className="border border-line-soft px-2 py-0.5 font-mono text-xs text-dim">
                          {r}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-dim">
                      Every repository on this account. Narrow it on GitHub if you would rather
                      pick specific ones.
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <ul className="mt-4 space-y-1.5 text-sm text-dim">
              {meta.permissions.map((p) => (
                <li key={p} className="flex gap-2">
                  <span className="text-faint">—</span> {p}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="shrink-0">
          {!available ? (
            <Micro>Not configured</Micro>
          ) : connected ? (
            <button
              onClick={onDisconnect}
              disabled={busy}
              className="btn-ghost hover:border-red hover:text-red"
            >
              {busy ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <button onClick={onConnect} disabled={busy} className="btn-primary">
              {busy ? (needsReauth ? "Reconnecting…" : "Connecting…") : needsReauth ? "Reconnect" : "Connect"}
            </button>
          )}
        </div>
      </div>

      {connected && meta.key === "github" && (
        <p className="mt-4 border-t border-line-soft pt-3 text-xs text-dim leading-relaxed">
          Disconnecting removes Mergit's stored access. The app installation itself lives on
          GitHub — remove it at{" "}
          <a
            href="https://github.com/settings/installations"
            target="_blank"
            rel="noreferrer"
            className="text-dim hover:text-text underline underline-offset-2 transition-colors"
          >
            github.com/settings/installations
          </a>{" "}
          to revoke it fully.
        </p>
      )}
    </Panel>
  );
}
