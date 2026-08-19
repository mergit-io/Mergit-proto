const ITEMS = [
  {
    title: "Leases, not locks",
    body: "A dead worker's task is reclaimed after 30 seconds — and that worker can no longer settle it.",
  },
  {
    title: "Keyed side effects",
    body: "Restart mid-run and the pull request is not opened a second time.",
  },
  {
    title: "Self-heal",
    body: "A repeating failure is fingerprinted, filed as an issue, and given its own fix goal.",
  },
  {
    title: "Model fallback",
    body: "A provider outage swaps models; a missing key pauses the task and asks you for it.",
  },
];

export function Reliability() {
  return (
    <section className="mx-auto max-w-[1240px] px-5 pb-20 sm:px-8 sm:pb-24">
      <div className="relative overflow-hidden rounded-[30px] bg-ink p-8 text-white sm:p-11">
        <div
          className="pointer-events-none absolute -right-24 -top-32 h-[520px] w-[520px] rounded-full bg-[radial-gradient(circle,rgba(109,74,255,0.42),transparent_66%)] blur-2xl"
          aria-hidden
        />
        <div className="relative grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-[#B9A9FF]">When it breaks</p>
            <h2 className="mb-3.5 font-sora text-[clamp(1.6rem,3vw,2.5rem)] font-bold leading-[1.1] tracking-[-0.03em]">
              Kill it mid-run. Nothing is lost, nothing repeats.
            </h2>
            <p className="text-[15px] leading-relaxed text-white/65">
              The parts nobody demos, because they only show up when something goes wrong.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-8">
            {ITEMS.map((i) => (
              <div key={i.title} className="rounded-[22px] border border-white/10 bg-white/[0.06] p-5">
                <p className="mb-2 text-base font-semibold">{i.title}</p>
                <p className="text-[13px] leading-relaxed text-white/65">{i.body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
