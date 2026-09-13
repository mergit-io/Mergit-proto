import { Eye, EyeOff, Globe, Mail } from "lucide-react";
import { useState } from "react";
import { createUserWithEmailAndPassword, signInWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { useNavigate } from "react-router-dom";
import { auth, githubProvider, googleProvider } from "../lib/firebase";

export function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [oauthLoading, setOauthLoading] = useState<"google" | "github" | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isSignUpMode, setIsSignUpMode] = useState(false);

  const startOAuth = async (provider: "google" | "github") => {
    try {
      setErrorMessage("");
      setOauthLoading(provider);
      const selectedProvider = provider === "google" ? googleProvider : githubProvider;
      await signInWithPopup(auth, selectedProvider);
      navigate("/app");
    } catch (error) {
      console.error(`${provider} sign-in failed`, error);
      setErrorMessage("Social sign in failed. Please try again.");
      setOauthLoading(null);
    }
  };

  const handleEmailAuth = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      setErrorMessage("");
      setSigningIn(true);
      if (isSignUpMode) {
        await createUserWithEmailAndPassword(auth, email.trim(), password);
      } else {
        await signInWithEmailAndPassword(auth, email.trim(), password);
      }
      navigate("/app");
    } catch (error: unknown) {
      console.error("Email sign in failed", error);
      setErrorMessage(
        isSignUpMode
          ? "Could not create account. Check email/password and try again."
          : "Invalid email or password. Please check and try again."
      );
      setSigningIn(false);
    }
  };

  return (
    <main className="min-h-screen bg-black text-white relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none opacity-25" style={{ backgroundImage: "radial-gradient(rgba(59,173,255,0.24) 1px, transparent 1px)", backgroundSize: "56px 56px" }} />
      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_50%_25%,rgba(48,81,255,0.24),transparent_55%)]" />

      <div className="relative max-w-7xl mx-auto px-6 py-8 min-h-screen">
        <header className="glass-card rounded-3xl px-8 py-4 flex items-center justify-between">
          <a href="/" className="flex items-center gap-3">
            <div className="grid grid-cols-2 gap-1 w-8 h-8">
              <div className="rounded bg-[#2d8cff]" />
              <div className="rounded bg-[#3f6cff]" />
              <div className="rounded bg-[#346dff]" />
              <div className="rounded bg-[#5f4dff]" />
            </div>
            <span className="font-display font-semibold text-3xl leading-none tracking-tight">omni<span className="text-[#2d8cff]">Box</span></span>
          </a>
          <button
            type="button"
            onClick={() => {
              setIsSignUpMode((v) => !v);
              setErrorMessage("");
            }}
            className="text-sm text-white/70 hover:text-white transition-colors"
          >
            {isSignUpMode ? "Already have an account? Sign in →" : "Need an account? Create one →"}
          </button>
        </header>

        <section className="relative min-h-[calc(100vh-120px)] grid lg:grid-cols-2 gap-10 items-center py-10">
          <div className="w-full text-center lg:text-left">
            <p className="inline-flex items-center gap-2 px-5 py-2 rounded-full border border-white/10 bg-white/5 text-[#2d8cff] font-semibold tracking-[0.16em] text-xs uppercase mb-6">
              <span className="w-2 h-2 rounded-full bg-[#2d8cff]" /> Now In Public Beta
            </p>
            <h1 className="font-display font-bold leading-[0.95] text-white text-[clamp(2.4rem,5.8vw,4.8rem)]">
              The Multi-Agent Platform
            </h1>
            <h2 className="font-display font-bold leading-[0.95] text-[clamp(2rem,5.2vw,4.3rem)] text-gradient-blue mt-2">
              for Autonomous AI
            </h2>
            <p className="mt-6 text-[clamp(0.95rem,1.25vw,1.15rem)] text-white/60 max-w-xl mx-auto lg:mx-0">
              Delegate any goal. omniBox decomposes it into a precise task graph, spins up specialized agents, invokes real tools, and delivers results end-to-end.
            </p>
          </div>

          <div className="w-full max-w-xl mx-auto lg:mx-0 glass-card rounded-3xl p-8 md:p-10">
            <h1 className="font-display text-5xl font-semibold leading-tight mb-2">
              {isSignUpMode ? "Create account." : "Welcome back."}
            </h1>
            <p className="text-text-muted mb-8">
              {isSignUpMode ? "Create your account to start delegating goals." : "Sign in to keep an eye on your agents."}
            </p>

            <form className="space-y-5" onSubmit={handleEmailAuth}>
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs text-text-muted">Email</label>
                  <div className="border-b border-white/15 focus-within:border-white/35 transition-colors">
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@company.com"
                      className="w-full bg-transparent py-2.5 outline-none text-white placeholder:text-white/35"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-xs text-text-muted">Password</label>
                  <div className="border-b border-white/15 focus-within:border-white/35 transition-colors flex items-center gap-2">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full bg-transparent py-2.5 outline-none text-white placeholder:text-white/35"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="text-white/45 hover:text-white/80 transition-colors"
                      aria-label="Toggle password visibility"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between text-sm">
                <label className="inline-flex items-center gap-2.5 cursor-pointer text-text-muted hover:text-white/85 transition-colors">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                    className="accent-white"
                  />
                  Remember me
                </label>
                <a href="#" className="text-text-muted hover:text-white/85 transition-colors">Forgot?</a>
              </div>

              <button
                type="submit"
                disabled={signingIn || oauthLoading !== null}
                className="w-full rounded-full h-12 flex items-center justify-center gap-2 disabled:opacity-60 bg-gradient-to-r from-[#2d8cff] to-[#6a4bff] text-white shadow-[0_0_32px_rgba(45,140,255,0.35)]"
              >
                <Mail className="w-4 h-4" />
                <span className="font-medium">
                  {signingIn ? (isSignUpMode ? "Creating account..." : "Signing in...") : (isSignUpMode ? "Create account" : "Sign in")}
                </span>
              </button>

              {errorMessage ? (
                <p className="text-xs text-red-300">{errorMessage}</p>
              ) : null}

              <div className="flex items-center gap-3 py-1">
                <div className="h-px flex-1 bg-white/10" />
                <span className="text-[11px] text-text-muted">or</span>
                <div className="h-px flex-1 bg-white/10" />
              </div>

              <div className="grid sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => startOAuth("google")}
                  disabled={oauthLoading !== null}
                  className="btn-glass rounded-lg h-11 text-sm font-medium disabled:opacity-60"
                >
                  {oauthLoading === "google" ? "Redirecting..." : "Continue with Google"}
                </button>
                <button
                  type="button"
                  onClick={() => startOAuth("github")}
                  disabled={oauthLoading !== null}
                  className="btn-glass rounded-lg h-11 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-60"
                >
                  <Globe className="w-4 h-4" />
                  {oauthLoading === "github" ? "Redirecting..." : "Continue with GitHub"}
                </button>
              </div>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}
