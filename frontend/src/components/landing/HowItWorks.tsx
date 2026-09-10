import { useCallback, useState } from "react";
import { Micro } from "../ui";
import { prefersReducedMotion } from "../../lib/motion";
import { RunStory } from "./RunStory";
import { RUN_STAGES } from "./runStages";

/* Two ways to tell the same four stages.
   ------------------------------------------------------------------------------
   The pinned story is the better argument — it spends scroll on the fact that
   each stage consumes what the last one produced — but it needs motion to be
   welcome and a viewport tall enough to hold a pinned stage. Everywhere else the
   stages are a grid of cards, which is the version that has to keep working: it
   is what a phone gets, what a reduced-motion visitor gets, and what is left if
   the motion chunk never arrives.

   The choice is made synchronously from `matchMedia`, before the first paint, so
   the section does not render one version and then swap. The only asynchronous
   path is failure: RunStory reports back if motion turns out to be unavailable,
   and the grid takes over. */
function StageGrid() {
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
          {RUN_STAGES.map((s, i) => (
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

function roomForAPinnedStage() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(min-width: 1024px) and (min-height: 680px)").matches
  );
}

export function HowItWorks() {
  const [pinned, setPinned] = useState(() => !prefersReducedMotion() && roomForAPinnedStage());
  const fallBackToGrid = useCallback(() => setPinned(false), []);

  return pinned ? <RunStory onUnavailable={fallBackToGrid} /> : <StageGrid />;
}
