import { Link } from "react-router-dom";
import { Micro, ProofBlock } from "../ui";
import { Replay } from "./Replay";
import { SylvaScene } from "./SylvaScene";

/* Both numbers are read off the system rather than chosen for the page:
   `economy.ROLES` is the six roles that hold a passport and earn reputation, and
   the fallback chain in backend/model_config.py is three providers deep — Groq,
   then Anthropic, then OpenRouter. If either changes, this copy is wrong, which
   is the point of citing them. */
const STATS = [
  { label: "Agent roles", value: "6 with passports", mark: "proof" },
  { label: "Provider tiers", value: "3 deep", mark: "chain" },
] as const;

function StatMark({ kind }: { kind: "proof" | "chain" }) {
  if (kind === "proof") return <ProofBlock className="w-full h-full" />;
  return (
    <svg viewBox="0 0 30 30" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <circle cx="15" cy="6.5" r="3.2" />
      <circle cx="7" cy="22" r="3.2" />
      <circle cx="23" cy="22" r="3.2" />
      <path d="M12.6 9.2 9.4 18.9M17.4 9.2l3.2 9.7M10.2 22h9.6" />
    </svg>
  );
}

export function HeroSection() {
  return (
    <section className="relative isolate flex min-h-[100svh] flex-col justify-end overflow-hidden">
      <SylvaScene className="absolute inset-0 -z-10" />
      {/* The world is bright at the horizon and the headline sits over it, so the
          type gets its own ground rather than a text-shadow — a wash dark enough
          to hold its contrast, shaped so the moss still reads through it. */}
      {/* pointer-events-none, or this wash sits over the whole hero and eats every
          move the scene's cursor parallax is listening for — the world would go
          still under a mouse that is plainly over it. */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        aria-hidden="true"
        style={{
          background:
            "linear-gradient(180deg, rgba(30,36,26,0.62) 0%, rgba(30,36,26,0.30) 34%, rgba(30,36,26,0.58) 78%, rgba(30,36,26,0.80) 100%)",
        }}
      />

      {/* The hero's copy is a layer over a world that tilts with the cursor, so the
          layer has to be transparent to the pointer everywhere it has nothing in it —
          otherwise a full-width wrapper's padding is enough to hold the whole scene
          still. Re-enabled per block rather than globally, so the type stays
          selectable and the card stays hoverable. */}
      <div className="pointer-events-none mx-auto w-full max-w-[1400px] px-5 pb-16 pt-32 lg:pb-24 lg:pt-40">
        <div className="grid items-end gap-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
          <div className="pointer-events-auto">
            <div className="flex items-center gap-2.5" data-reveal>
              <span className="h-1.5 w-1.5 bg-violet" />
              <Micro>Proof of work · on chain</Micro>
            </div>

            {/* Lexend at 300, not Archivo at 700: the console's display face is a
                slab that fights the scene. The landing borrows Sylva's face for the
                one headline and hands the page straight back afterwards. */}
            <h1
              className="font-moss mt-7 text-[clamp(2.6rem,6.4vw,5.25rem)] font-light leading-[0.98] tracking-[-0.028em]"
              data-reveal
              style={{ "--reveal-delay": "80ms" } as React.CSSProperties}
            >
              Describe the outcome.
              <br />
              <span className="text-dim">Not the steps.</span>
            </h1>

            <p
              className="mt-8 max-w-xl text-base leading-relaxed text-dim"
              data-reveal
              style={{ "--reveal-delay": "160ms" } as React.CSSProperties}
            >
              Mergit takes one sentence, decomposes it into a task graph, and puts specialised
              agents to work with real tools — reading repositories, running code, opening pull
              requests. Every finished task mints a proof and moves its agent's reputation.
            </p>

            <div
              className="mt-10 flex flex-wrap items-center gap-4"
              data-reveal
              style={{ "--reveal-delay": "240ms" } as React.CSSProperties}
            >
              <Link to="/app" className="moss-pill">
                Delegate a goal
                <span aria-hidden="true">&rarr;</span>
              </Link>
              {/* Sylva's play control, pointed at something real: the run below. */}
              <a href="#run" className="moss-ring" aria-label="See a full run">
                <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
                  <path d="M8 5.2v13.6L19 12z" fill="currentColor" />
                </svg>
              </a>
            </div>

            <dl
              className="mt-12 flex flex-wrap gap-3"
              data-reveal
              style={{ "--reveal-delay": "320ms" } as React.CSSProperties}
            >
              {STATS.map((s) => (
                <div key={s.label} className="moss-stat">
                  <span className="h-6 w-6 shrink-0 text-violet" aria-hidden="true">
                    <StatMark kind={s.mark} />
                  </span>
                  <div>
                    <dt className="font-mono text-micro uppercase text-dim">{s.label}</dt>
                    <dd className="mt-1 text-sm">{s.value}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>

          {/* Sylva's cream field-note card, holding the run instead of a photograph.
              It is the one light surface on the page, which is what makes the run
              read as the subject rather than as decoration. */}
          <div
            className="moss-card pointer-events-auto"
            data-reveal
            style={{ "--reveal-delay": "400ms" } as React.CSSProperties}
          >
            <Replay compact />
          </div>
        </div>

        <a href="#run" className="moss-scroll pointer-events-auto mt-14" data-reveal>
          Discover
          <span className="moss-track" aria-hidden="true" />
        </a>
      </div>
    </section>
  );
}
