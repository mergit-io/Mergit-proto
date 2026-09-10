import { Suspense, lazy, useState } from "react";
import { Link } from "react-router-dom";
import { ProofBlock } from "../ui";
import { hasWebGL } from "../../lib/webgl";

/* The object is a further chunk beyond this page's own: three.js is ~170KB
   gzipped and the hero's type, grid and copy should not wait behind it. Until it
   arrives — and on any machine that cannot give us a GL context — the plate holds
   the line-art mark, which is the same object drawn flat. */
const ProofObject = lazy(() =>
  import("./ProofObject").then((m) => ({ default: m.ProofObject }))
);

/* One object, one sentence, one control, and a great deal of nothing. */
export function NextHero() {
  // Probed once, at mount: the answer cannot change while the page is open.
  const [webgl] = useState(hasWebGL);

  return (
    <section className="mx-auto max-w-[1320px] px-8 pb-28 pt-40 lg:pb-40 lg:pt-52">
      <div className="grid items-center gap-16 lg:grid-cols-[1fr_0.9fr] lg:gap-24">
        <div>
          <p className="paper-eyebrow">Proof of work · on chain</p>

          <h1 className="font-display mt-8 text-[clamp(2.9rem,6vw,4.9rem)] font-bold leading-[0.94] tracking-tightest">
            Describe the outcome.{" "}
            <br />
            <span className="text-dim">Not the steps.</span>
          </h1>

          <p className="mt-8 max-w-lg text-[17px] leading-relaxed text-dim">
            Mergit takes one sentence, decomposes it into a task graph, and puts specialised
            agents to work with real tools. Every finished task hashes its output and mints a
            proof on chain.
          </p>

          <div className="mt-11 flex flex-wrap items-center gap-8">
            <Link to="/app" className="paper-cta paper-cta--lg">
              Delegate a goal
            </Link>
            <a href="#run" className="paper-link">
              See how a run works
            </a>
          </div>
        </div>

        <div className="paper-plate">
          {webgl ? (
            <Suspense fallback={<ProofBlock className="h-2/3 w-2/3 text-violet" />}>
              <ProofObject className="absolute inset-0" />
            </Suspense>
          ) : (
            <ProofBlock className="h-2/3 w-2/3 text-violet" />
          )}
        </div>
      </div>
    </section>
  );
}
