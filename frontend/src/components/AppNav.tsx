import { LayoutDashboard, ExternalLink, Cpu, GitBranch, Trophy, Plug, ShieldAlert } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { WalletConnect } from "./WalletConnect";

/**
 * Top navigation for every /app page.
 *
 * Automate, Self-Heal and Actions are deliberately not listed. Their routes still exist and
 * still work — /app/webhooks, /app/heal and /app/actions are reachable by URL and from the
 * pages that link to them — they are simply not top-level destinations for a first-time user.
 *
 * Below the `nav` breakpoint the same destinations move to a scrollable second row rather
 * than being hidden: a nav that collapses to nothing on a phone is not a responsive nav, it
 * is a dead end. That breakpoint is 1080px rather than `md` or `lg` because the single-row
 * layout needs 1062px, and below that it silently drew the destinations on top of the
 * external links instead of wrapping.
 */

const DESTINATIONS = [
  { to: "/app", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/app/models", label: "Models", Icon: Cpu },
  { to: "/app/connections", label: "Connections", Icon: Plug },
  { to: "/app/approvals", label: "Approvals", Icon: ShieldAlert },
  { to: "/app/economy", label: "Economy", Icon: Trophy },
];

const EXTERNAL = [
  { href: "/api/docs", label: "API docs", Icon: ExternalLink },
  { href: "https://github.com/mergit-io/Mergit-proto", label: "GitHub", Icon: GitBranch },
];

export function AppNav() {
  const nav = useNavigate();
  const { pathname } = useLocation();

  const navBtn = (to: string, label: string, Icon: React.ComponentType<{ className?: string }>) => {
    const active = pathname === to;
    return (
      <button
        key={to}
        onClick={() => nav(to)}
        className={`flex shrink-0 items-center gap-1.5 rounded-[10px] px-3 py-2 text-[13px] font-medium transition-colors ${
          active ? "bg-[#F1EBFF] text-[#5B4BA8]" : "text-ink-muted hover:bg-ink/[0.04] hover:text-ink"
        }`}
      >
        <Icon className="h-3.5 w-3.5" />
        {label}
      </button>
    );
  };

  const extLink = (href: string, label: string, Icon: React.ComponentType<{ className?: string }>) => (
    <a
      key={href}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex shrink-0 items-center gap-1.5 rounded-[10px] px-3 py-2 text-[13px] font-medium text-ink-muted transition-colors hover:bg-ink/[0.04] hover:text-ink"
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </a>
  );

  return (
    <header className="sticky top-0 z-40 border-b border-ink/[0.07] bg-white/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-5 py-2.5 sm:px-8">
        <div className="flex min-w-0 items-center gap-6">
          <button onClick={() => nav("/")} className="flex shrink-0 items-center gap-2.5">
            <svg viewBox="0 0 32 32" className="h-[22px] w-[22px]" fill="none" aria-hidden>
              <circle cx="8" cy="8" r="4" fill="#6D4AFF" />
              <circle cx="24" cy="8" r="4" fill="#FF8A5C" />
              <path
                d="M8 12 C8 18, 16 16, 16 22 M24 12 C24 18, 16 16, 16 22"
                stroke="#6D4AFF"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
              <circle cx="16" cy="24.5" r="4.5" fill="#10B981" />
            </svg>
            <span className="font-sora text-base font-bold tracking-tight text-ink">Mergit</span>
          </button>

          <nav className="hidden min-w-0 items-center gap-1 overflow-x-auto nav:flex [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {DESTINATIONS.map((d) => navBtn(d.to, d.label, d.Icon))}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <div className="hidden items-center gap-1 nav:flex">
            {EXTERNAL.map((e) => extLink(e.href, e.label, e.Icon))}
          </div>
          <WalletConnect />
        </div>
      </div>

      {/* Below the `nav` breakpoint the destinations live here instead of disappearing. */}
      <nav className="flex items-center gap-1 overflow-x-auto px-4 pb-2.5 nav:hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {DESTINATIONS.map((d) => navBtn(d.to, d.label, d.Icon))}
        {EXTERNAL.map((e) => extLink(e.href, e.label, e.Icon))}
      </nav>
    </header>
  );
}
