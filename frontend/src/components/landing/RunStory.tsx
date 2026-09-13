import { useEffect, useRef } from "react";
import { Micro } from "../ui";
import { loadMotion } from "../../lib/motion";
import { RUN_STAGES } from "./runStages";

/* The run, told as one scroll.
   ------------------------------------------------------------------------------
   The four stages used to be four cards side by side, which is an accurate
   summary and a poor argument: a reader takes them in at a glance and never
   learns that each stage consumes what the last one produced. Pinned, the section
   spends the reader's scroll on that sequence instead — the heading holds still,
   and the stage under it advances one beat at a time.

   The scroll drives it (`scrub`), so nothing plays on its own: stop moving and
   the story stops with you, scroll back and it runs backwards. That is the whole
   reason to pin rather than autoplay.

   Rendered only when motion is available and the viewport can hold a pinned
   stage — HowItWorks falls back to the card grid otherwise. */

const AGENTS = ["orchestrator", "researcher", "coder", "integrator"];
const DIGEST = "9f2c4b17e8a0c31d…41ab";

export function RunStory({ onUnavailable }: { onUnavailable: () => void }) {
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const actsRef = useRef<(HTMLDivElement | null)[]>([]);
  const railRef = useRef<HTMLSpanElement>(null);
  const edgesRef = useRef<(SVGPathElement | null)[]>([]);
  const nodesRef = useRef<(SVGRectElement | null)[]>([]);
  const barsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const receiptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      const motion = await loadMotion();
      if (cancelled) return;
      if (!motion) {
        // No motion means no way to advance the beats, and three of the four are
        // hidden. Hand the section back to the card grid rather than show one.
        onUnavailable();
        return;
      }
      const { gsap } = motion;
      const section = sectionRef.current;
      const stage = stageRef.current;
      const acts = actsRef.current.filter((el): el is HTMLDivElement => Boolean(el));
      if (!section || !stage || acts.length !== RUN_STAGES.length) return;

      const context = gsap.context(() => {
        // Only the first beat is on screen to begin with.
        gsap.set(acts.slice(1), { autoAlpha: 0, yPercent: 4 });

        const timeline = gsap.timeline({
          defaults: { ease: "none" },
          scrollTrigger: {
            trigger: section,
            start: "top top",
            // One viewport of scroll per beat after the first, plus a tail so the
            // last beat is readable before the section lets go.
            end: () => `+=${window.innerHeight * (RUN_STAGES.length - 1) + window.innerHeight * 0.6}`,
            pin: stage,
            pinSpacing: true,
            anticipatePin: 1,
            scrub: 0.6,
            invalidateOnRefresh: true,
          },
        });

        // The rail runs the whole length, so it reads as progress through the run
        // rather than progress through an animation.
        if (railRef.current) {
          timeline.fromTo(
            railRef.current,
            { scaleX: 0 },
            { scaleX: 1, duration: RUN_STAGES.length - 1 + 0.6 },
            0
          );
        }

        acts.forEach((act, i) => {
          if (i === 0) return;
          const at = i - 0.4;
          timeline
            .to(acts[i - 1], { autoAlpha: 0, yPercent: -4, duration: 0.4 }, at)
            .to(act, { autoAlpha: 1, yPercent: 0, duration: 0.4 }, at);
        });

        // Beat two draws the graph it is describing.
        const edges = edgesRef.current.filter(Boolean) as SVGPathElement[];
        const nodes = nodesRef.current.filter(Boolean) as SVGRectElement[];
        edges.forEach((edge) => {
          const length = edge.getTotalLength();
          gsap.set(edge, { strokeDasharray: length, strokeDashoffset: length });
        });
        gsap.set(nodes, { transformOrigin: "50% 50%", scale: 0.4, autoAlpha: 0.25 });
        timeline
          .to(nodes, { scale: 1, autoAlpha: 1, duration: 0.5, stagger: 0.06 }, 0.7)
          .to(edges, { strokeDashoffset: 0, duration: 0.5, stagger: 0.05 }, 0.85);

        // Beat three runs them.
        const bars = barsRef.current.filter(Boolean) as HTMLSpanElement[];
        gsap.set(bars, { transformOrigin: "0% 50%", scaleX: 0 });
        timeline.to(bars, { scaleX: 1, duration: 0.55, stagger: 0.07 }, 1.75);

        // Beat four settles.
        if (receiptRef.current) {
          timeline.fromTo(
            receiptRef.current,
            { autoAlpha: 0, yPercent: 18 },
            { autoAlpha: 1, yPercent: 0, duration: 0.4 },
            2.85
          );
        }
      }, section);

      cleanup = () => context.revert();
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [onUnavailable]);

  return (
    <section id="run" ref={sectionRef} className="border-t border-line">
      <div ref={stageRef} className="run-stage">
        <div className="mx-auto w-full max-w-[1400px] px-5">
          <div className="max-w-2xl">
            <Micro>The run</Micro>
            <h2 className="font-moss mt-4 text-[clamp(1.9rem,4vw,3.1rem)] font-light leading-[1.02] tracking-[-0.02em]">
              From one sentence
              <br />
              to a merged pull request.
            </h2>
          </div>

          {/* The visible beats are all aria-hidden: three of the four are
              `visibility: hidden` at any moment, so a screen reader walking the
              page linearly would meet stage one and nothing else. This is the
              same four stages as prose, in order, read once. */}
          <ol className="sr-only">
            {RUN_STAGES.map((stage, i) => (
              <li key={stage.title}>
                <h3>{`Stage ${i + 1}. ${stage.title}`}</h3>
                <p>{stage.body}</p>
                <p>{`Produces: ${stage.out}`}</p>
              </li>
            ))}
          </ol>

          <div className="relative mt-12 h-[440px]" aria-hidden="true">
            {RUN_STAGES.map((stage, i) => (
              <div
                key={stage.title}
                ref={(el) => {
                  actsRef.current[i] = el;
                }}
                className="absolute inset-0 grid gap-10 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16"
                aria-hidden="true"
                style={i === 0 ? undefined : { opacity: 0, visibility: "hidden" }}
              >
                <div>
                  <span className="font-moss text-5xl font-light leading-none text-faint">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="font-moss mt-6 text-2xl font-normal tracking-tight">
                    {stage.title}
                  </h3>
                  <p className="mt-4 max-w-md text-sm leading-relaxed text-dim">{stage.body}</p>
                  <div className="mt-6 inline-flex">
                    <span className="glass-label">{stage.out}</span>
                  </div>
                </div>

                <div className="story-panel">
                  {i === 0 && (
                    <div className="flex h-full flex-col justify-center">
                      <span className="glass-label">One sentence</span>
                      <p className="font-moss mt-4 text-xl font-light leading-snug">
                        “Audit mergit-io/proto for security issues and open PRs with fixes”
                      </p>
                    </div>
                  )}

                  {i === 1 && (
                    <div className="flex h-full items-center justify-center">
                      {/* The shape the orchestrator actually emits: one plan node,
                          three tasks that can run at once, one that waits for them. */}
                      <svg viewBox="0 0 320 190" className="h-auto w-full max-w-[440px]" aria-hidden="true">
                        <g stroke="rgb(var(--c-violet))" strokeWidth="1.1" fill="none">
                          {[
                            "M160 34 C160 60, 60 62, 60 88",
                            "M160 34 C160 60, 160 62, 160 88",
                            "M160 34 C160 60, 260 62, 260 88",
                            "M60 112 C60 138, 160 140, 160 156",
                            "M160 112 C160 138, 160 140, 160 156",
                            "M260 112 C260 138, 160 140, 160 156",
                          ].map((d, e) => (
                            <path
                              key={d}
                              d={d}
                              ref={(el) => {
                                edgesRef.current[e] = el;
                              }}
                            />
                          ))}
                        </g>
                        <g fill="rgb(var(--c-text))">
                          {[
                            [148, 22],
                            [48, 88],
                            [148, 88],
                            [248, 88],
                            [148, 156],
                          ].map(([x, y], n) => (
                            <rect
                              key={`${x}-${y}`}
                              x={x}
                              y={y}
                              width="24"
                              height="24"
                              ref={(el) => {
                                nodesRef.current[n] = el;
                              }}
                            />
                          ))}
                        </g>
                      </svg>
                    </div>
                  )}

                  {i === 2 && (
                    <ul className="flex h-full flex-col justify-center gap-4">
                      {AGENTS.map((agent, a) => (
                        <li key={agent}>
                          <span className="flex items-center justify-between">
                            <span className="font-mono text-micro uppercase text-dim">{agent}</span>
                            <span className="font-mono text-micro uppercase text-violet">
                              tool call
                            </span>
                          </span>
                          <span className="mt-2 block h-px w-full bg-line">
                            <span
                              className="block h-px w-full bg-violet"
                              ref={(el) => {
                                barsRef.current[a] = el;
                              }}
                            />
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {i === 3 && (
                    <div className="flex h-full flex-col justify-center">
                      <span className="glass-label">SHA-256 of the output</span>
                      <p className="mt-3 break-all font-mono text-sm text-dim">{DIGEST}</p>
                      <div
                        className="proof-field mt-6 flex items-center justify-between rounded-2xl px-4 py-3"
                        ref={receiptRef}
                      >
                        <span className="glass-label">Proof minted</span>
                        <span className="font-mono text-xs tabular">0x9f2c…41ab</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-14 flex items-center gap-4">
            <span className="relative block h-px flex-1 bg-line">
              <span
                className="absolute inset-0 block origin-left bg-violet"
                ref={railRef}
                aria-hidden="true"
              />
            </span>
            <span className="glass-label">Scroll</span>
          </div>
        </div>
      </div>
    </section>
  );
}
