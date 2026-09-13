import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Micro, ProofBlock } from "../ui";

/* The hero's argument is the run itself: one real goal, decomposed, executed by
   four agents, settled on chain. It replays on a loop rather than being described. */
const STEPS = [
  { agent: "orchestrator", act: "Decomposed the goal into 4 tasks", tool: "plan", ms: 1400 },
  { agent: "researcher", act: "Read the repo and located the flaw", tool: "github_read_file", ms: 2000 },
  { agent: "coder", act: "Wrote the patch and ran it", tool: "code_exec", ms: 2200 },
  { agent: "integrator", act: "Opened pull request #42", tool: "github_pr", ms: 1800 },
];

const GOAL = "Audit mergit-io/proto for security issues and open PRs with fixes";
const RECEIPT = "0x9f2c4b17e8a0…41ab";

function useReplay(count: number, paused: boolean) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStep(count + 1);
      return;
    }
    if (paused) return;
    // `step` runs one past the last row so the settled receipt gets its own beat.
    const delay = step > count ? 3200 : (STEPS[step]?.ms ?? 1200);
    const t = setTimeout(() => setStep((s) => (s > count ? 0 : s + 1)), delay);
    return () => clearTimeout(t);
  }, [step, count, paused]);

  return [step, setStep] as const;
}

function Replay() {
  // Hovering holds the run still so a step can actually be read, and clicking a
  // step jumps to it — the panel is the page's main claim, so it is worth being
  // able to inspect rather than only watch.
  const [paused, setPaused] = useState(false);
  const [step, setStep] = useReplay(STEPS.length, paused);
  const settled = step > STEPS.length;

  return (
    <div
      className="panel"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      // Focus holds it too — a keyboard user tabbing the steps had no way to stop the
      // run moving under them.
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <Micro>Live run</Micro>
        <span className="flex items-center gap-2">
          <span
            className={`w-1.5 h-1.5 transition-colors duration-300 ${
              paused ? "bg-amber" : settled ? "bg-mint" : "bg-violet animate-blip"
            }`}
          />
          <Micro>{paused ? "Held" : settled ? "Settled" : "Executing"}</Micro>
        </span>
      </div>

      <div className="px-4 py-3.5 border-b border-line">
        <Micro>Goal</Micro>
        <p className="text-sm mt-1.5 leading-snug">{GOAL}</p>
      </div>

      <ol>
        {STEPS.map((s, i) => {
          const done = step > i;
          const active = step === i;
          return (
            <li
              key={s.agent}
              className="border-b border-line-soft"
              aria-current={active ? "step" : undefined}
            >
              {/* A button may only contain phrasing content, so the row is spans, and
                  the dimming sits on an inner wrapper — on the button it also faded the
                  focus ring, leaving keyboard focus almost invisible on queued steps.
                  No aria-label: it would replace the whole subtree for a screen reader
                  and swallow the status, the tool name and the progress. */}
              <button
                onClick={() => setStep(i)}
                className="w-full text-left px-4 py-3 block transition-colors duration-300 hover:bg-raise"
              >
                <span
                  className={`block transition-opacity duration-300 ${
                    done || active ? "opacity-100" : "opacity-40"
                  }`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-mono text-micro uppercase text-dim">
                      {String(i + 1).padStart(2, "0")} · {s.agent}
                    </span>
                    <span
                      className={`font-mono text-micro uppercase ${
                        done ? "text-mint" : active ? "text-violet" : "text-faint"
                      }`}
                    >
                      {done ? "Done" : active ? "Running" : "Queued"}
                    </span>
                  </span>
                  <span className="block text-sm mt-1.5">{s.act}</span>
                  <span className="flex items-center gap-3 mt-2">
                    <code className="font-mono text-micro text-dim">{s.tool}()</code>
                    <span className="flex-1 h-px bg-line relative overflow-hidden">
                      {done && <span className="absolute inset-0 bg-mint" />}
                      {active && <span className="absolute inset-0 bar-indeterminate" />}
                    </span>
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {/* The settled receipt: the moment the run becomes a fact on chain. */}
      <div
        className={`flex items-center justify-between px-4 py-3.5 transition-colors duration-500 ${
          settled ? "proof-field" : "bg-slab"
        }`}
      >
        <Micro>{settled ? "Proof minted" : "Awaiting settlement"}</Micro>
        <span className={`font-mono text-xs tabular ${settled ? "" : "text-faint"}`}>
          {settled ? RECEIPT : "—"}
        </span>
      </div>
    </div>
  );
}

export function HeroSection() {
  return (
    <section className="max-w-[1400px] mx-auto px-5 pt-32 pb-20 lg:pt-44 lg:pb-28">
      <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-10 lg:gap-16 items-center">
        <div>
          <div className="flex items-center gap-2.5">
            <ProofBlock className="w-4 h-4 text-violet" />
            <Micro>Proof of work · on chain</Micro>
          </div>

          <h1 className="font-display font-bold tracking-tightest leading-[0.9] mt-6 text-[clamp(2.75rem,7vw,5.5rem)]">
            Describe the
            <br />
            outcome.
            <br />
            <span className="text-dim">Not the steps.</span>
          </h1>

          <p className="text-base text-dim mt-7 max-w-lg leading-relaxed">
            Mergit takes one sentence, decomposes it into a task graph, and puts specialised
            agents to work with real tools — reading repositories, running code, opening pull
            requests. Every finished task mints a proof and moves its agent's reputation.
          </p>

          <div className="flex flex-wrap gap-px mt-9">
            <Link to="/app" className="btn-primary h-11 px-6">
              Delegate a goal →
            </Link>
            <a href="#run" className="btn-ghost h-11 px-6">
              See a full run
            </a>
          </div>
        </div>

        <Replay />
      </div>
    </section>
  );
}
