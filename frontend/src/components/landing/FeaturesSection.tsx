import { Micro } from "../ui";

/* The roster is a spec sheet, not a feature grid: each agent's model and the tools
   it is actually allowed to reach. Scope is the interesting fact, so it is a table. */
const AGENTS = [
  {
    mark: "RS",
    role: "Researcher",
    model: "Llama 3.3 70B",
    does: "Reads repositories file by file, pulls issue detail, searches code by symbol, and returns structured findings.",
    tools: ["github_read_file", "github_list_dir", "github_get_issue", "web_search", "spawn_goal"],
  },
  {
    mark: "WR",
    role: "Writer",
    model: "Llama 3.3 70B",
    does: "Turns findings into something a person reads — reports, architecture notes, pull request descriptions, Mermaid diagrams.",
    tools: ["file_ops"],
  },
  {
    mark: "CD",
    role: "Coder",
    model: "Llama 3.3 70B",
    does: "Writes runnable Python, executes it in a subprocess with a 30-second limit, and only submits once the output is what it expected.",
    tools: ["code_exec", "file_ops", "github_read_file"],
  },
  {
    mark: "IN",
    role: "Integrator",
    model: "Llama 3.3 70B",
    does: "Acts on the outside world: opens pull requests, comments on issues, creates repositories, sets branch protection, waits on webhooks.",
    tools: ["github_pr", "github_post_comment", "github_create_repo", "wait_webhook"],
  },
];

/* Facts about behaviour under failure. Stated flat, because the claim is the point. */
const GUARANTEES = [
  ["Crash mid-task", "Resumes from the same step on restart"],
  ["Lease expires", "Reclaimed within 30 seconds and retried"],
  ["Tool call repeats", "Hash-matched and served from the stored result"],
  ["Task exhausts retries", "Orchestrator replans an alternative route"],
  ["Mergit's own bug", "Files the issue, then spawns a goal to fix it"],
];

export function FeaturesSection() {
  return (
    <section id="agents" className="border-t border-line">
      <div className="max-w-[1400px] mx-auto px-5 py-20 lg:py-28">
        <div className="max-w-2xl mb-14" data-reveal>
          <Micro>The roster</Micro>
          <h2 className="font-display font-bold tracking-tightest leading-[0.95] mt-4 text-[clamp(2rem,4.5vw,3.5rem)]">
            Four specialists.
            <br />
            Scoped on purpose.
          </h2>
          <p className="text-sm text-dim mt-5 leading-relaxed">
            An agent can only reach the tools its role is given. The researcher cannot open a
            pull request; the coder cannot post to GitHub. Nothing has blanket access.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-px">
          {AGENTS.map((a, i) => (
            <article
              key={a.role}
              data-reveal
              style={{ "--reveal-delay": `${i * 70}ms` } as React.CSSProperties}
              className="panel p-6 lg:p-7 transition-colors duration-300 hover:bg-raise"
            >
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 border border-line flex items-center justify-center font-mono text-micro text-dim">
                  {a.mark}
                </span>
                <h3 className="font-display font-semibold text-xl tracking-tight">{a.role}</h3>
                <span className="ml-auto">
                  <Micro>{a.model}</Micro>
                </span>
              </div>

              <p className="text-sm text-dim mt-5 leading-relaxed">{a.does}</p>

              <div className="rule mt-6 pt-4">
                <Micro>Tools</Micro>
                <ul className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2.5">
                  {a.tools.map((t) => (
                    <li key={t} className="font-mono text-xs text-dim">
                      {t}
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </div>

        <div className="panel mt-px" data-reveal>
          <div className="border-b border-line px-4 py-2.5">
            <Micro>What happens when it goes wrong</Micro>
          </div>
          <table className="dtable">
            <tbody>
              {GUARANTEES.map(([when, then]) => (
                <tr key={when}>
                  <td className="w-1/3 font-mono text-micro uppercase text-dim">{when}</td>
                  <td>{then}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
