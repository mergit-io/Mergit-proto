import { useNavigate } from "react-router-dom";
import { GLBackground } from "../GLBackground";
import { RunReplay } from "./RunReplay";
import { useChainBadge } from "../../hooks/useChainBadge";

export function Hero() {
  const nav = useNavigate();
  const chain = useChainBadge();

  return (
    <section className="relative overflow-hidden pb-16">
      {/* CSS mesh — also the fallback if WebGL is unavailable */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-36 -top-64 h-[720px] w-[780px] rounded-full bg-[radial-gradient(circle_at_40%_40%,#E4D6FF,rgba(228,214,255,0)_68%)] blur-2xl" />
        <div className="absolute -right-40 -top-52 h-[700px] w-[760px] rounded-full bg-[radial-gradient(circle_at_60%_40%,#FFDCC6,rgba(255,220,198,0)_66%)] blur-2xl" />
        <div className="absolute left-[44%] top-60 h-[560px] w-[640px] rounded-full bg-[radial-gradient(circle_at_50%_50%,#C9F3E2,rgba(201,243,226,0)_66%)] blur-3xl" />
        <GLBackground className="absolute inset-0 block h-full w-full opacity-95 [filter:blur(12px)saturate(1.1)] [mask-image:radial-gradient(ellipse_46%_40%_at_50%_30%,rgba(0,0,0,0.34)_0%,rgba(0,0,0,0.78)_48%,#000_80%)]" />
      </div>

      <div className="relative mx-auto flex max-w-[1000px] flex-col items-center gap-5 px-5 pt-14 text-center sm:px-8 sm:pt-16">
        <span className="inline-flex items-center gap-2 rounded-full border border-proof/30 bg-white/80 py-1.5 pl-3 pr-4">
          <span
            className={`h-1.5 w-1.5 rounded-full ${chain.live ? "bg-proof shadow-[0_0_0_4px_rgba(16,185,129,0.18)]" : "bg-ink-dim"}`}
          />
          <span className="font-mono text-xs uppercase tracking-wide text-[#12775C]">{chain.label}</span>
        </span>

        <h1 className="font-sora text-[clamp(2.5rem,7vw,4.6rem)] font-extrabold leading-[1.03] tracking-[-0.035em] text-ink [text-wrap:balance]">
          Delegate the goal.
          <br />
          <span className="bg-gradient-to-r from-accent via-[#7C3AED] to-proof-deep bg-clip-text text-transparent">
            Keep the proof.
          </span>
        </h1>

        <p className="max-w-[600px] text-base leading-relaxed text-ink-muted sm:text-[17px]">
          Say what you want in one sentence. Four specialist agents plan it, run it against real
          tools, and leave a hash of every finished task on a chain you can check.
        </p>

        <div className="flex flex-col items-stretch gap-3 pt-1 sm:flex-row sm:items-center">
          <button
            onClick={() => nav("/app")}
            className="inline-flex h-[52px] items-center justify-center gap-2.5 rounded-[18px] bg-ink px-7 text-base font-semibold text-white shadow-[0_24px_46px_-26px_rgba(26,23,37,0.9)] transition-transform hover:-translate-y-0.5"
          >
            Start a goal
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </button>
          <a
            href="#how-it-runs"
            className="inline-flex h-[52px] items-center justify-center rounded-[18px] border border-ink/10 bg-white/80 px-6 text-base font-medium text-ink transition-colors hover:bg-white"
          >
            See how it runs
          </a>
        </div>
      </div>

      <div className="relative mx-auto mt-11 max-w-[1180px] px-4 sm:px-8">
        <RunReplay />
        <p className="mx-auto mt-3.5 max-w-[900px] text-center font-mono text-[11px] leading-relaxed text-ink-dim">
          Every task, output, hash, block number and contract address above is read from the live
          API. Only the pacing is authored — the recorded run finished faster than a person can read it.
        </p>
      </div>
    </section>
  );
}
