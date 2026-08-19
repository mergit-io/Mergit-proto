const AGENTS = [
  {
    role: "Researcher",
    body: "Reads issues, diffs and repo files, searches the web, and comes back with sources — never a claim it has not read.",
    meta: "12 tools",
    tint: "bg-[#F1EBFF]",
    stroke: "#6D4AFF",
    icon: (
      <>
        <circle cx="11" cy="11" r="6" />
        <path d="M20 20l-4.5-4.5" />
      </>
    ),
  },
  {
    role: "Writer",
    body: "Turns the findings into the thing you actually asked for — the report, the summary, the document body.",
    meta: "structured output",
    tint: "bg-[#FFF0E7]",
    stroke: "#FF8A5C",
    icon: (
      <>
        <path d="M5 20h14" />
        <path d="M15.5 4.5l4 4L9 19H5v-4z" />
      </>
    ),
  },
  {
    role: "Coder",
    body: "Writes the patch and runs it. Code that leaves a function unimplemented is refused, not shipped.",
    meta: "code_exec · file_ops",
    tint: "bg-[#E9F9F2]",
    stroke: "#10B981",
    icon: (
      <>
        <path d="M9 6l-5 6 5 6" />
        <path d="M15 6l5 6-5 6" />
      </>
    ),
  },
  {
    role: "Integrator",
    body: "Owns GitHub: pull requests, comments, labels, reviews, merges and branch protection.",
    meta: "20 operations",
    tint: "bg-[#EBF1FF]",
    stroke: "#3C5BA8",
    icon: (
      <>
        <circle cx="7" cy="6" r="2.5" />
        <circle cx="7" cy="18" r="2.5" />
        <circle cx="17" cy="12" r="2.5" />
        <path d="M7 8.5v7M9.5 17l5-3.6M9.5 7l5 3.6" />
      </>
    ),
  },
];

export function Agents() {
  return (
    <section id="agents" className="border-t border-ink/[0.06] bg-gradient-to-b from-[#FBF9FF] to-paper">
      <div className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-24">
        <div className="mx-auto mb-11 max-w-[620px] text-center">
          <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">The team</p>
          <h2 className="mb-3.5 font-sora text-[clamp(1.9rem,4vw,3.1rem)] font-bold leading-[1.08] tracking-[-0.035em] text-ink">
            Four agents. Each kept to its own lane.
          </h2>
          <p className="text-base leading-relaxed text-ink-muted">
            An agent can only call the tools its role allows — that list lives in the registry, not
            the prompt.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {AGENTS.map((a) => (
            <div
              key={a.role}
              className="flex flex-col gap-3 rounded-[26px] border border-ink/[0.08] bg-white p-7 shadow-[0_30px_60px_-60px_rgba(26,23,37,0.8)]"
            >
              <span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${a.tint}`}>
                <svg
                  viewBox="0 0 24 24"
                  className="h-5 w-5"
                  fill="none"
                  stroke={a.stroke}
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  {a.icon}
                </svg>
              </span>
              <p className="font-sora text-xl font-bold text-ink">{a.role}</p>
              <p className="text-[13px] leading-relaxed text-ink-muted">{a.body}</p>
              <span className="mt-auto font-mono text-[11px] text-ink-dim">{a.meta}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
