import { LayoutDashboard, ExternalLink, Cpu, GitBranch, Zap, Workflow, Trophy, HeartPulse } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { WalletConnect } from "./WalletConnect";

export function AppNav() {
  const nav = useNavigate();
  const { pathname } = useLocation();

  const navBtn = (to: string, label: string, Icon: React.ComponentType<{ className?: string }>) => {
    const active = pathname === to;
    return (
      <button
        onClick={() => nav(to)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
          active
            ? "bg-white/8 text-white"
            : "text-text-muted hover:text-white hover:bg-white/4"
        }`}
      >
        <Icon className="w-3.5 h-3.5" />
        {label}
      </button>
    );
  };

  return (
    <header className="sticky top-0 z-40 border-b border-white/6 bg-black/80 backdrop-blur-md">
      <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <button
          onClick={() => nav("/")}
          className="flex items-center gap-2 group"
        >
          <svg viewBox="0 0 32 32" fill="none" className="w-6 h-6">
            <defs>
              <linearGradient id="app-nav-logo-line" x1="4" y1="10" x2="28" y2="10" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6d4aff" />
                <stop offset="1" stopColor="#22d3ee" />
              </linearGradient>
            </defs>
            <circle cx="8" cy="8" r="4" fill="#6d4aff" />
            <circle cx="24" cy="8" r="4" fill="#22d3ee" />
            <path
              d="M8 12 C8 18, 16 16, 16 22 M24 12 C24 18, 16 16, 16 22"
              stroke="url(#app-nav-logo-line)"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
            <circle cx="16" cy="24.5" r="4.5" fill="#2eff9e" />
          </svg>
          <span className="font-display font-bold text-base text-white tracking-tight">
            Merg<span className="text-gradient-blue">it</span>
          </span>
        </button>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {navBtn("/app", "Dashboard", LayoutDashboard)}
          {navBtn("/app/models", "Models", Cpu)}
          {navBtn("/app/webhooks", "Automate", Zap)}
          {navBtn("/app/heal", "Self-Heal", HeartPulse)}
          {navBtn("/app/actions", "Actions", Workflow)}
          {navBtn("/app/economy", "Economy", Trophy)}
          <a
            href="/api/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-text-muted hover:text-white hover:bg-white/4 transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            API Docs
          </a>
          <a
            href="https://github.com/mergit-io/Mergit-proto"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-text-muted hover:text-white hover:bg-white/4 transition-all"
          >
            <GitBranch className="w-3.5 h-3.5" />
            GitHub
          </a>
          <WalletConnect />
        </nav>
      </div>
    </header>
  );
}
