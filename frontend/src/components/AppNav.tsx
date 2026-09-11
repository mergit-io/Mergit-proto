import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useTheme } from "../lib/theme";
import { useChainBadge } from "../hooks/useChainBadge";
import { WalletConnect } from "./WalletConnect";
import { Micro } from "./ui";

/* The bar carries the four things a run passes through — delegate it, watch it reach the
   apps, approve what needs a human, read the proof — and nothing else. The rest are real
   pages that are not part of that path: setup (Models, Connections), triggers (Automate,
   Actions) and the repair log (Self-Heal). They moved behind `More` rather than being
   deleted, because eight equal-weight tabs meant the bar ranked nothing, and a link
   removed outright would have broken every route that still points at it. */
const LINKS = [
  { to: "/app", label: "Dashboard", end: true },
  { to: "/app/services", label: "Services" },
  { to: "/app/approvals", label: "Approvals" },
  { to: "/app/economy", label: "Economy" },
];

const MORE = [
  { to: "/app/connections", label: "Connections", hint: "Grant and revoke app access" },
  { to: "/app/models", label: "Models", hint: "Which model runs which agent" },
  { to: "/app/webhooks", label: "Automate", hint: "Start a goal from an event" },
  { to: "/app/actions", label: "Actions", hint: "One-off repository actions" },
  { to: "/app/heal", label: "Self-Heal", hint: "What broke, and what fixed it" },
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

const NAV_ITEM =
  "px-3 h-14 flex items-center font-mono text-micro uppercase whitespace-nowrap border-b-2 -mb-px transition-colors";

/** The overflow menu. Everything in it is a page, not a mode — so it is a plain list of
    links with a line of copy each, rather than a control that changes what the bar does. */
function MoreMenu() {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  const active = MORE.some((m) => pathname.startsWith(m.to));

  // Closed by a click anywhere else and by Escape. Without the first, the menu stays open
  // over the page after a mis-click; without the second it is a keyboard trap.
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  // A route change closes it, including one made from inside the menu itself.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="relative" ref={box}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="true"
        className={`${NAV_ITEM} ${
          active ? "border-violet text-text" : "border-transparent text-dim hover:text-text"
        }`}
      >
        More
        <span aria-hidden="true" className="ml-1.5 text-[9px] leading-none">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 w-64 border border-line bg-slab shadow-lg">
          {MORE.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              className={({ isActive }) =>
                `block px-4 py-3 border-b border-line-soft last:border-0 transition-colors ${
                  isActive ? "text-text" : "text-dim hover:text-text"
                }`
              }
            >
              <span className="font-mono text-micro uppercase">{m.label}</span>
              <span className="block text-xs text-dim mt-0.5">{m.hint}</span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export function AppNav() {
  const chain = useChainBadge();

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-ink/92 backdrop-blur-md">
      <div className="max-w-[1400px] mx-auto px-5 h-14 flex items-center gap-5">
        <Wordmark to="/app" />

        <nav className="flex items-center flex-1 min-w-0" aria-label="Console">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `${NAV_ITEM} ${
                  isActive
                    ? "border-violet text-text"
                    : "border-transparent text-dim hover:text-text"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
          <MoreMenu />
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
