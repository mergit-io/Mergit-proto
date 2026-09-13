import { Link, NavLink, useLocation } from "react-router-dom";
import { useTheme } from "../lib/theme";
import { useChainBadge } from "../hooks/useChainBadge";
import { WalletConnect } from "./WalletConnect";
import { Micro } from "./ui";

const LINKS = [
  { to: "/app", label: "Dashboard", end: true },
  { to: "/app/models", label: "Models" },
  { to: "/app/webhooks", label: "Automate" },
  { to: "/app/actions", label: "Actions" },
  { to: "/app/connections", label: "Connections" },
  { to: "/app/approvals", label: "Approvals" },
  { to: "/app/heal", label: "Self-Heal" },
  { to: "/app/economy", label: "Economy" },
];

/** The wordmark: a violet square standing in for a minted proof, then the name. */
export function Wordmark({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2.5 shrink-0 group" aria-label="Mergit home">
      <span className="w-3.5 h-3.5 bg-violet group-hover:bg-violet-hi transition-colors" />
      <span className="font-display font-bold text-[15px] tracking-tight uppercase">Mergit</span>
    </Link>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      className="h-9 px-3 border border-line text-dim hover:text-text hover:border-faint font-mono text-micro uppercase transition-colors"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}

export function AppNav() {
  const chain = useChainBadge();

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-ink/92 backdrop-blur-md">
      <div className="max-w-[1400px] mx-auto px-5 h-14 flex items-center gap-5">
        <Wordmark to="/app" />

        <nav className="flex items-center overflow-x-auto flex-1 min-w-0" aria-label="Console">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `px-3 h-14 flex items-center font-mono text-micro uppercase whitespace-nowrap border-b-2 -mb-px transition-colors ${
                  isActive
                    ? "border-violet text-text"
                    : "border-transparent text-dim hover:text-text"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          <span
            className="hidden lg:flex items-center gap-2 h-9 px-3 border border-line"
            title={chain.label}
          >
            <span className={`w-1.5 h-1.5 ${chain.live ? "bg-mint animate-blip" : "bg-faint"}`} />
            <Micro>{chain.label}</Micro>
          </span>
          <ThemeToggle />
          <WalletConnect />
        </div>
      </div>
    </header>
  );
}

/** Standard page frame: the bar, then a gutter-bounded column of panels. */
export function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen flex flex-col">
      <AppNav />
      {/* Keyed on the route so moving between pages replays the settle, which
          makes navigation feel like a step rather than a repaint. */}
      <main
        key={pathname}
        className={`enter flex-1 w-full mx-auto px-5 py-10 ${wide ? "max-w-[1400px]" : "max-w-6xl"}`}
      >
        {children}
      </main>
    </div>
  );
}
