import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Micro, Notice, Panel, ProofBlock } from "../components/ui";
import { useAuth } from "../lib/auth";

/**
 * One way in: Google.
 *
 * The page this replaces offered Google, GitHub and email/password, all through Firebase.
 * GitHub is deliberately gone from here, and that is a product decision rather than a
 * simplification: signing in *with* GitHub grants Mergit nothing *on* GitHub. A user who
 * clicked it would reasonably assume otherwise, and would then be confused about why
 * Mergit still asks them to connect GitHub afterwards. GitHub lives on the Connections
 * page, where it means what it looks like it means.
 *
 * Email/password is gone for a duller reason: it is a password to store, reset, breach and
 * support, in exchange for nothing this product needs.
 */
export function Login() {
  const { user, authConfigured, loading } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  useEffect(() => {
    if (!loading && user) navigate("/app", { replace: true });
  }, [loading, user, navigate]);

  const notice = params.get("auth") ?? (params.get("expired") ? "expired" : "");

  return (
    <div className="min-h-screen flex items-center justify-center px-5 py-16">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 mb-8">
          <ProofBlock className="w-4 h-4 text-violet" />
          <span className="font-display font-bold text-[15px] tracking-tight uppercase">Mergit</span>
        </div>

        <h1 className="font-display font-bold tracking-tightest leading-[0.95] text-4xl">
          Sign in to
          <br />
          run agents.
        </h1>
        <p className="text-sm text-dim mt-4 leading-relaxed">
          Mergit uses Google only to identify you. Granting access to your repositories is a
          separate step, and you choose what each connection may do.
        </p>

        {notice && (
          <div className="mt-6">
            <Notice tone="wait">
              {notice === "expired"
                ? "Your session ended. Sign in again to pick up where you left off."
                : "That sign-in did not finish. Start it again."}
            </Notice>
          </div>
        )}

        {!authConfigured ? (
          // Fail loudly rather than showing a button that cannot work. The instinct is
          // inherited from the page this replaces, and it was the right one.
          <div className="mt-6">
            <Panel title="Sign-in is not configured" bodyClass="px-4 py-4 space-y-3">
              <p className="text-sm text-dim leading-relaxed">
                Set{" "}
                <code className="font-mono text-xs bg-raise px-1.5 py-0.5">
                  OAUTH_GOOGLE_CLIENT_ID
                </code>{" "}
                and{" "}
                <code className="font-mono text-xs bg-raise px-1.5 py-0.5">
                  OAUTH_GOOGLE_CLIENT_SECRET
                </code>{" "}
                on the backend to turn it on.
              </p>
              <p className="text-sm text-dim leading-relaxed">
                Until then Mergit runs single-tenant and the console is open to anyone who can
                reach it.
              </p>
              <a href="/app" className="btn-primary w-full">
                Open the console →
              </a>
            </Panel>
          </div>
        ) : (
          <div className="mt-8">
            {/* A plain link, not fetch(). The OAuth flow is a full-page redirect to
                Google — an XHR cannot follow it, and the state/nonce Authlib stores on
                this response has to reach the browser as a real navigation. */}
            <a href="/api/auth/login" className="btn-primary w-full h-11 gap-3">
              <GoogleMark />
              Continue with Google
            </a>
            <p className="mt-6">
              <Micro>Connections are granted later, one at a time</Micro>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.7v3h3.9c2.3-2.1 3.5-5.2 3.5-8.9z" />
      <path fill="#34A853" d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.9-3c-1.1.7-2.4 1.2-4 1.2-3.1 0-5.7-2.1-6.6-4.9H1.4v3.1A12 12 0 0 0 12 24z" />
      <path fill="#FBBC05" d="M5.4 14.4a7.2 7.2 0 0 1 0-4.6V6.7H1.4a12 12 0 0 0 0 10.8l4-3.1z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.4 6.7l4 3.1C6.3 6.9 8.9 4.8 12 4.8z" />
    </svg>
  );
}
