import { useNavigate } from "react-router-dom";

export function ClosingCta() {
  const nav = useNavigate();

  return (
    <section className="relative overflow-hidden border-t border-ink/[0.06]">
      <div
        className="pointer-events-none absolute -bottom-72 left-1/2 h-[700px] w-[1040px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(228,214,255,0.85),rgba(255,220,198,0.5)_44%,transparent_70%)] blur-3xl"
        aria-hidden
      />
      <div className="relative mx-auto max-w-[1000px] px-5 py-24 text-center sm:px-8">
        <h2 className="mx-auto mb-4 max-w-[720px] font-sora text-[clamp(2rem,5vw,3.6rem)] font-extrabold leading-[1.05] tracking-[-0.035em] text-ink">
          Give it a goal you would hand to a junior engineer.
        </h2>
        <p className="mx-auto mb-8 max-w-[500px] text-base leading-relaxed text-ink-muted sm:text-[17px]">
          Then read the graph, the tool calls, and the proof it leaves behind.
        </p>
        <button
          onClick={() => nav("/app")}
          className="inline-flex h-[54px] items-center gap-2.5 rounded-[18px] bg-accent px-8 text-base font-semibold text-white shadow-[0_26px_50px_-26px_rgba(109,74,255,0.95)] transition-transform hover:-translate-y-0.5"
        >
          Launch app
          <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M3 8h10M9 4l4 4-4 4" />
          </svg>
        </button>
      </div>
    </section>
  );
}
