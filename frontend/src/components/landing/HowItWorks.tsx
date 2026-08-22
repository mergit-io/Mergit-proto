import { Micro } from "../ui";

/* Numbered because the stages are genuinely ordered: each one consumes what the
   previous produced. The numbers carry information rather than decorating. */
const STAGES = [
  {
    title: "You describe an outcome",
    body: "One sentence in plain language. No template to fill in, no workflow to wire up, no step list to keep current.",
    out: "Natural language",
  },
  {
    title: "The orchestrator draws the graph",
    body: "A planning model turns that sentence into a task graph — every node assigned to an agent, with its inputs and dependencies resolved.",
    out: "Task DAG",
  },
  {
    title: "Agents execute in parallel",
    body: "Up to five tasks run at once. Each agent works a tool-call loop against real systems, and every call is checked for idempotency before it fires.",
    out: "Real side effects",
  },
  {
    title: "The work settles",
    body: "The final task returns the result — a pull request, a repository, a report. Each finished task hashes its output and mints a proof on chain.",
    out: "Result and proof",
  },
];

export function HowItWorks() {
  return (
    <section id="run" className="border-t border-line">
      <div className="max-w-[1400px] mx-auto px-5 py-20 lg:py-28">
        <div className="max-w-2xl mb-14" data-reveal>
          <Micro>The run</Micro>
          <h2 className="font-display font-bold tracking-tightest leading-[0.95] mt-4 text-[clamp(2rem,4.5vw,3.5rem)]">
            From one sentence
            <br />
            to a merged pull request.
          </h2>
        </div>

        <ol className="grid md:grid-cols-2 xl:grid-cols-4 gap-px">
          {STAGES.map((s, i) => (
            <li
              key={s.title}
              data-reveal
              style={{ "--reveal-delay": `${i * 70}ms` } as React.CSSProperties}
              className="panel flex flex-col p-6 lg:p-7 transition-colors duration-300 hover:bg-raise"
            >
              <span className="font-display font-bold text-5xl leading-none tracking-tightest text-faint">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="font-display font-semibold text-lg tracking-tight mt-6">{s.title}</h3>
              <p className="text-sm text-dim mt-3 leading-relaxed flex-1">{s.body}</p>
              <div className="rule mt-6 pt-3">
                <Micro>{s.out}</Micro>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
