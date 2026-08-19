const STEPS = [
  {
    n: "01 · 02",
    title: "Stated, then planned",
    body: "Your sentence is stored, then Claude turns it into a task graph — and a validator rejects a bad plan before any worker sees it.",
    refs: ["POST /api/goals", "orchestrator.py"],
    span: "lg:col-span-5",
    tone: "bg-gradient-to-br from-[#F3EEFF] to-[#FBF9FF] border-accent/15",
  },
  {
    n: "03",
    title: "Leased to the right agent",
    body: "Up to five ready tasks run at once. Each is claimed under a fenced lease, so a worker that dies hands its task back instead of stalling the run.",
    refs: ["worker.py"],
    span: "lg:col-span-7",
    tone: "bg-white border-ink/[0.08]",
  },
  {
    n: "04",
    title: "Real tools, fired once",
    body: "Pull requests, web searches, sandboxed Python, webhook waits. Every side-effecting call carries a key, so a retry after a crash is not a second write.",
    refs: ["github_pr", "web_search", "code_exec", "wait_webhook"],
    span: "lg:col-span-7",
    tone: "bg-white border-ink/[0.08]",
  },
  {
    n: "05",
    title: "The proof lands",
    body: "The output is hashed, written to the chain, and the agent's reputation moves with it.",
    refs: ["chain/ · contracts/"],
    span: "lg:col-span-5",
    tone: "bg-gradient-to-br from-[#E9FBF4] to-[#FBFEFD] border-proof/20",
  },
];

export function HowItRuns() {
  return (
    <section id="how-it-runs" className="mx-auto max-w-[1240px] px-5 py-20 sm:px-8 sm:py-24">
      <div className="mb-10 max-w-[640px]">
        <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">How it runs</p>
        <h2 className="mb-3.5 font-sora text-[clamp(1.9rem,4vw,3.1rem)] font-bold leading-[1.08] tracking-[-0.035em] text-ink">
          You write one line. Five things happen.
        </h2>
        <p className="text-base leading-relaxed text-ink-muted">
          And you can watch all five of them, live, while they happen.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {STEPS.map((s) => (
          <div key={s.title} className={`rounded-[26px] border p-7 ${s.tone} ${s.span}`}>
            <span className="font-mono text-xs text-accent">{s.n}</span>
            <p className="mt-3 font-sora text-xl font-bold text-ink sm:text-2xl">{s.title}</p>
            <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">{s.body}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {s.refs.map((r) => (
                <span
                  key={r}
                  className="rounded-lg bg-white/80 px-2.5 py-1.5 font-mono text-[11px] text-[#5B4BA8]"
                >
                  {r}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
