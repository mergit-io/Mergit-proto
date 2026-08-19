const REPO = "https://github.com/mergit-io/Mergit-proto";

export function SiteFooter() {
  return (
    <footer className="mx-auto flex max-w-[1240px] flex-col items-center justify-between gap-4 border-t border-ink/[0.07] px-5 py-9 sm:flex-row sm:px-8">
      <div className="flex items-center gap-2.5">
        <svg viewBox="0 0 32 32" className="h-5 w-5" fill="none" aria-hidden>
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
        <span className="text-[13px] text-ink-dim">Mergit — open source agent runtime</span>
      </div>
      <div className="flex items-center gap-6 text-[13px] text-ink-dim">
        <a href="/api/docs" className="transition-colors hover:text-ink">
          API docs
        </a>
        <a href={REPO} target="_blank" rel="noopener noreferrer" className="transition-colors hover:text-ink">
          GitHub
        </a>
        <a href="#proof" className="transition-colors hover:text-ink">
          Proof economy
        </a>
      </div>
    </footer>
  );
}
