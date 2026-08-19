import { useNavigate } from "react-router-dom";

const LINKS = [
  { label: "How it runs", href: "#how-it-runs" },
  { label: "Agents", href: "#agents" },
  { label: "Proof", href: "#proof" },
  { label: "Docs", href: "/api/docs" },
];

export function LandingNav() {
  const nav = useNavigate();

  return (
    <header className="relative z-30 flex justify-center px-4 pt-5 sm:px-8">
      <nav className="aurora-nav flex w-full max-w-[1200px] items-center justify-between gap-6 rounded-[22px] py-2.5 pl-5 pr-2.5 sm:pl-6">
        <a href="/" className="flex shrink-0 items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="h-6 w-6" fill="none" aria-hidden>
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
          <span className="font-sora text-lg font-extrabold tracking-tight text-ink">Mergit</span>
        </a>

        <ul className="hidden items-center gap-7 md:flex">
          {LINKS.map((l) => (
            <li key={l.label}>
              <a
                href={l.href}
                className="text-sm font-medium text-ink-muted transition-colors hover:text-ink"
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>

        <button
          onClick={() => nav("/app")}
          className="shrink-0 rounded-[14px] bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-[0_16px_30px_-18px_rgba(109,74,255,0.95)] transition-transform hover:-translate-y-0.5"
        >
          Launch app
        </button>
      </nav>
    </header>
  );
}
