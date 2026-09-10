import { Link } from "react-router-dom";
import { CHAIN, RECEIPTS, STACK } from "../landing/content";
import { RUN_STAGES } from "../landing/runStages";

/* The editorial half of /next: the same claims the moss landing makes, set on
   paper. The genre's whole argument is the grid and the whitespace, so the
   sections share one measure, one hairline weight and one vertical rhythm, and
   nothing is boxed in a panel. */

function SectionHead({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="max-w-2xl">
      <p className="paper-eyebrow">{label}</p>
      <h2 className="font-display mt-6 text-[clamp(2rem,4vw,3.2rem)] font-bold leading-[0.98] tracking-tightest">
        {children}
      </h2>
    </div>
  );
}

export function RunEditorial() {
  return (
    <section id="run" className="paper-section">
      <SectionHead label="The run">
        From one sentence
        <br />
        to a merged pull request.
      </SectionHead>

      <ol className="mt-16 border-t border-line">
        {RUN_STAGES.map((stage, i) => (
          <li
            key={stage.title}
            className="grid gap-6 border-b border-line py-10 md:grid-cols-[5rem_1fr_11rem] md:gap-12 md:py-12"
          >
            <span className="font-display text-3xl font-bold leading-none tracking-tightest text-faint">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="max-w-xl">
              <h3 className="font-display text-xl font-semibold tracking-tight">{stage.title}</h3>
              <p className="mt-3 leading-relaxed text-dim">{stage.body}</p>
            </div>
            <p className="paper-eyebrow md:text-right">{stage.out}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ProofEditorial() {
  return (
    <section id="proof" className="paper-section">
      <div className="grid gap-16 lg:grid-cols-[1fr_1fr] lg:gap-24">
        <div>
          <SectionHead label="Proof of work">
            A finished task
            <br />
            is a fact, not a claim.
          </SectionHead>
          <p className="mt-8 max-w-md leading-relaxed text-dim">
            Agents assert that they did the work. Mergit hashes what they produced and writes it
            to an EVM chain, so the claim can be checked by anyone rather than trusted. Run it
            locally and the chain runs in-process; point it at Monad testnet and the same proofs
            land in public.
          </p>

          <table className="mt-12 w-full border-t border-line">
            <caption className="paper-eyebrow py-4 text-left">Latest receipts</caption>
            <tbody>
              {RECEIPTS.map((r) => (
                <tr key={r.tx} className="border-b border-line-soft">
                  <td className="py-3.5 font-mono text-sm">{r.tx}</td>
                  <td className="py-3.5 font-mono text-micro uppercase text-dim">{r.role}</td>
                  <td className="py-3.5 text-right font-mono text-sm text-violet">{r.rep} rep</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ol className="lg:pt-6">
          {CHAIN.map(([title, body], i) => (
            <li key={title} className="border-b border-line py-7 first:border-t">
              <div className="flex items-baseline gap-5">
                <span className="font-mono text-micro uppercase text-faint">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="font-display text-lg font-semibold tracking-tight">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-dim">{body}</p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function StackEditorial() {
  return (
    <section id="stack" className="paper-section">
      <div className="grid gap-16 lg:grid-cols-[0.8fr_1.2fr] lg:gap-24">
        <div>
          <SectionHead label="The stack">
            Chosen for
            <br />
            what breaks.
          </SectionHead>
          <p className="mt-8 max-w-sm leading-relaxed text-dim">
            Each piece is here because of how it behaves on a bad day — when a provider caps out,
            when the process dies mid-task, when a model is swapped without a restart.
          </p>
        </div>

        <table className="w-full border-t border-line">
          <tbody>
            {STACK.map((s) => (
              <tr key={s.name} className="border-b border-line-soft">
                <td className="w-56 py-4 font-mono text-micro uppercase">{s.name}</td>
                <td className="py-4 text-sm text-dim">{s.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function NextFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-[1320px] px-8 py-24 lg:py-32">
        <div className="flex flex-wrap items-end justify-between gap-10">
          <h2 className="font-display max-w-xl text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-[1] tracking-tightest">
            Give it an outcome
            <br />
            and read the receipts.
          </h2>
          <Link to="/app" className="paper-cta paper-cta--lg">
            Delegate a goal
          </Link>
        </div>

        <div className="mt-20 flex flex-wrap items-center justify-between gap-6 border-t border-line pt-8">
          <p className="text-sm text-dim">Mergit — the AI agent economy</p>
          <div className="flex items-center gap-8 text-sm">
            <a
              href="https://github.com/mergit-io/Mergit-proto"
              target="_blank"
              rel="noopener noreferrer"
              className="text-dim transition-colors hover:text-text"
            >
              GitHub
            </a>
            <Link to="/" className="text-dim transition-colors hover:text-text">
              The other landing
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
