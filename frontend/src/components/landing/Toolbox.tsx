const GROUPS = [
  {
    label: "Repo work",
    tools: [
      "github_pr",
      "github_review_pr",
      "github_merge_pr",
      "github_create_issue",
      "github_read_file",
      "github_create_repo",
    ],
    extra: "+14 more",
    chip: "bg-[#F1EEFF] text-[#4C3BB0]",
    note: null,
  },
  {
    label: "Outside world",
    tools: ["web_search", "http_request", "wait_webhook"],
    extra: null,
    chip: "bg-[#E7F7FB] text-[#077C94]",
    note: "A task can park on a webhook and wake up when the event arrives, without holding a worker.",
  },
  {
    label: "Machine work",
    tools: ["code_exec", "file_ops", "spawn_goal"],
    extra: null,
    chip: "bg-ink/[0.06] text-[#2B3446]",
    note: "An agent that finds a bigger problem can spawn a whole new goal instead of guessing at it.",
  },
];

export function Toolbox() {
  return (
    <section className="mx-auto max-w-[1240px] px-5 pb-20 sm:px-8 sm:pb-24">
      <div className="mb-9 max-w-[620px]">
        <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">The toolbox</p>
        <h2 className="mb-3.5 font-sora text-[clamp(1.9rem,4vw,3.1rem)] font-bold leading-[1.08] tracking-[-0.035em] text-ink">
          Real side effects, fired exactly once.
        </h2>
        <p className="text-base leading-relaxed text-ink-muted">
          Every side-effecting call carries an idempotency key, so a retry after a crash is not a
          second pull request.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {GROUPS.map((g) => (
          <div key={g.label} className="rounded-[22px] border border-ink/[0.08] bg-white p-6">
            <p className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">{g.label}</p>
            <div className="flex flex-wrap gap-2">
              {g.tools.map((t) => (
                <span key={t} className={`rounded-lg px-2.5 py-1.5 font-mono text-[11px] ${g.chip}`}>
                  {t}
                </span>
              ))}
              {g.extra && (
                <span className="rounded-lg bg-ink/[0.05] px-2.5 py-1.5 font-mono text-[11px] text-ink-muted">
                  {g.extra}
                </span>
              )}
            </div>
            {g.note && <p className="mt-4 text-[13px] leading-relaxed text-ink-muted">{g.note}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
