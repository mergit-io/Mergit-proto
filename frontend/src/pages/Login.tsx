import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppBackground } from "../components/AppBackground";
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
    <div className="relative min-h-screen" style={{ background: "#FFFDFB" }}>
      <AppBackground />
      <div className="relative z-10 min-h-screen flex items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-semibold text-ink tracking-tight">Mergit</h1>
            <p className="mt-2 text-sm text-ink/50">
              Sign in to run agents on your own repositories.
            </p>
          </div>

          {notice && (
            <div className="mb-5 rounded-xl border border-amber-400/25 bg-amber-400/10 px-4 py-3 text-sm text-amber-200/90">
              {notice === "expired"
                ? "Your session expired. Sign in again to continue."
                : "That sign-in did not complete. Please try again."}
            </div>
          )}

          {!authConfigured ? (
            // Fail loudly rather than showing a button that cannot work. The instinct is
            // inherited from the page this replaces, and it was the right one.
            <div className="rounded-xl border border-ink/[0.09] bg-white/[0.03] p-5 text-sm text-ink/60 space-y-2">
              <p className="text-ink/85 font-medium">Sign-in is not configured</p>
              <p>
                Set <code className="text-ink/80">OAUTH_GOOGLE_CLIENT_ID</code> and{" "}
                <code className="text-ink/80">OAUTH_GOOGLE_CLIENT_SECRET</code> on the
                backend. Until then Mergit runs in single-tenant mode and{" "}
                <a href="/app" className="text-ink underline underline-offset-2">
                  the app is open
                </a>
                .
              </p>
            </div>
          ) : (
            <>
              {/* A plain link, not fetch(). The OAuth flow is a full-page redirect to
                  Google — an XHR cannot follow it, and the state/nonce Authlib stores on
                  this response has to reach the browser as a real navigation. */}
              <a
                href="/api/auth/login"
                className="flex items-center justify-center gap-3 w-full rounded-xl bg-white px-4 py-3
                           text-sm font-medium text-black transition-all hover:bg-ink/[0.04]"
              >
                <GoogleMark />
                Continue with Google
              </a>

              <p className="mt-5 text-center text-xs leading-relaxed text-ink/35">
                Mergit only uses Google to identify you. Connecting GitHub or Slack is a
                separate step, and you choose exactly what each one may do.
              </p>
            </>
          )}
        </div>
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
