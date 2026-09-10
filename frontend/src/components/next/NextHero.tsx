import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ProofBlock } from "../ui";
import { hasWebGL } from "../../lib/webgl";
import { loadMotion } from "../../lib/motion";
import type { ProofObjectHandle } from "./ProofObject";

/* The object is a further chunk beyond this page's own: three.js is ~170KB
   gzipped and the hero's type, grid and copy should not wait behind it. Until it
   arrives — and on any machine that cannot give us a GL context — the plate holds
   the line-art mark, which is the same object drawn flat. */
const ProofObject = lazy(() =>
  import("./ProofObject").then((m) => ({ default: m.ProofObject }))
);

/* The digest the object is carrying. The same string the run story mints, so the
   two pages describe one ledger. */
const DIGEST = "9f2c4b17e8a0c31d…41ab";

/* One object, one sentence, one control, and a great deal of nothing. */
export function NextHero() {
  // Probed once, at mount: the answer cannot change while the page is open.
  const [webgl] = useState(hasWebGL);
  const sectionRef = useRef<HTMLElement>(null);
  const digestRef = useRef<HTMLDivElement>(null);
  const objectRef = useRef<ProofObjectHandle | null>(null);

  /* Stable, or the object would tear itself down and rebuild its GL context on
     every render of this component. */
  const onHandle = useCallback((handle: ProofObjectHandle | null) => {
    objectRef.current = handle;
  }, []);

  /* Scrolling out of the hero opens the block: the halves part, the core
     brightens, and the digest it was holding becomes readable. Scrubbed, so it is
     the reader doing it rather than a thing that plays at them — and reversible,
     which is the whole difference between this and a video.

     The digest is HTML over the canvas rather than a texture on a face. Text
     drawn into WebGL at this size is soft, unselectable and invisible to a screen
     reader; here it is none of those things. */
  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      const motion = await loadMotion();
      const digest = digestRef.current;
      if (cancelled) return;

      if (!motion) {
        // No motion: the block stays sealed and the digest is simply legible,
        // rather than being information locked behind a scroll that never runs.
        if (digest) digest.style.opacity = "1";
        return;
      }

      const section = sectionRef.current;
      if (!section) return;

      const trigger = motion.ScrollTrigger.create({
        trigger: section,
        start: "top top",
        /* Exactly the scroll during which this section still fills the window,
           which is exactly how long the sticky plate stays framed. Ending on the
           section's foot instead ran the choreography for a screenful longer than
           the object was visible, so it finished opening above the fold. */
        end: () => `+=${Math.max(240, section.offsetHeight - window.innerHeight)}`,
        invalidateOnRefresh: true,
        scrub: 0.4,
        onUpdate: (self) => {
          objectRef.current?.setProgress(self.progress);
          if (digest) {
            const t = (self.progress - 0.42) / 0.34;
            digest.style.opacity = String(Math.min(1, Math.max(0, t)));
          }
        },
      });

      cleanup = () => trigger.kill();
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);

  return (
    <section ref={sectionRef} className="mx-auto max-w-[1320px] px-8 pb-28 pt-40 lg:pt-52">
      {/* `items-start` and a sticky plate: the copy scrolls past while the object
          stays framed, which is the only way the opening is watchable — mapped to
          the section's whole height, the block finished opening somewhere above
          the top of the window. */}
      <div className="grid items-center gap-16 lg:grid-cols-[1fr_0.9fr] lg:items-start lg:gap-24">
        {/* The copy carries the section's extra height rather than the section
            itself: a sticky child sticks within its own grid, and a grid is only
            as tall as its tallest item. Padding here is what the plate travels
            against. */}
        <div className="lg:pb-[42vh]">
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

        <div className="paper-plate lg:sticky lg:top-28">
          {webgl ? (
            <Suspense fallback={<ProofBlock className="h-2/3 w-2/3 text-violet" />}>
              <ProofObject className="absolute inset-0" onHandle={onHandle} />
            </Suspense>
          ) : (
            <ProofBlock className="h-2/3 w-2/3 text-violet" />
          )}

          <div
            ref={digestRef}
            className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-4 border-t border-line px-6 py-4 opacity-0"
          >
            <span className="paper-eyebrow">SHA-256 of the output</span>
            <span className="font-mono text-sm">{DIGEST}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
