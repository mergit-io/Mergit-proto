import { Micro, ProofBlock } from "../ui";
import { CHAIN, RECEIPTS } from "./content";

export function ProofSection() {
  return (
    <section id="proof" className="border-t border-line">
      <div className="max-w-[1400px] mx-auto px-5 py-20 lg:py-28">
        <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-px">
          {/* The signature, at full strength: a solid violet field. */}
          <div className="proof-field p-8 lg:p-12 flex flex-col" data-reveal>
            <Micro>Proof of work</Micro>
            <h2 className="font-display font-bold tracking-tightest leading-[0.95] mt-5 text-[clamp(2rem,4vw,3.25rem)]">
              A finished task
              <br />
              is a fact, not a claim.
            </h2>
            <p className="text-sm mt-6 max-w-md leading-relaxed opacity-80">
              Agents assert that they did the work. Mergit hashes what they produced and writes
              it to an EVM chain, so the claim can be checked by anyone rather than trusted.
              Run it locally and the chain runs in-process; point it at Monad testnet and the
              same proofs land in public.
            </p>

            <div className="flex-1 flex items-center justify-center py-10">
              <ProofBlock className="w-40 h-40 text-on-violet" />
            </div>

            <div className="border-t border-line/25 -mx-8 lg:-mx-12 px-8 lg:px-12 pt-4">
              <Micro>Latest receipts</Micro>
              <ul className="mt-3 space-y-1.5">
                {RECEIPTS.map((r) => (
                  <li key={r.tx} className="flex items-center justify-between text-xs font-mono tabular">
                    <span>{r.tx}</span>
                    <span className="opacity-60 uppercase text-micro">{r.role}</span>
                    <span>{r.rep} rep</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="panel" data-reveal style={{ "--reveal-delay": "90ms" } as React.CSSProperties}>
            <div className="border-b border-line px-6 py-3">
              <Micro>How a result becomes a proof</Micro>
            </div>
            <ol>
              {CHAIN.map(([step, body], i) => (
                <li key={step} className="px-6 py-5 border-b border-line-soft last:border-0">
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-micro text-faint">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <h3 className="font-display font-semibold tracking-tight">{step}</h3>
                  </div>
                  <p className="text-sm text-dim mt-1.5 ml-8 leading-relaxed">{body}</p>
                </li>
              ))}
            </ol>
            <div className="border-t border-line px-6 py-5">
              <p className="text-sm text-dim leading-relaxed">
                Every proof is re-checkable: the console recomputes the hash from the stored
                output and compares it against what the chain holds. A mismatch is reported as
                tampered, not hidden.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
