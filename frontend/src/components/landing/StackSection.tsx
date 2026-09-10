import { Micro } from "../ui";
import { STACK } from "./content";

export function StackSection() {
  return (
    <section id="stack" className="border-t border-line">
      <div className="max-w-[1400px] mx-auto px-5 py-20 lg:py-24">
        <div className="grid lg:grid-cols-[0.8fr_1.2fr] gap-10 lg:gap-16">
          <div data-reveal>
            <Micro>The stack</Micro>
            <h2 className="font-display font-bold tracking-tightest leading-[0.95] mt-4 text-[clamp(1.75rem,3.5vw,2.75rem)]">
              Chosen for
              <br />
              what breaks.
            </h2>
            <p className="text-sm text-dim mt-5 leading-relaxed">
              Each piece is here because of how it behaves on a bad day — when a provider caps
              out, when the process dies mid-task, when a model is swapped without a restart.
            </p>
          </div>

          <div className="panel" data-reveal style={{ "--reveal-delay": "90ms" } as React.CSSProperties}>
            <table className="dtable">
              <tbody>
                {STACK.map((s) => (
                  <tr key={s.name}>
                    <td className="w-52 font-mono text-micro uppercase">{s.name}</td>
                    <td className="text-dim">{s.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
