import { useEffect, useState } from "react";
import run from "../../data/recorded-run.json";

/**
 * Replays a real completed run in the hero.
 *
 * Every task, output, hash, block number and contract address comes from `recorded-run.json`,
 * which is generated from the live API by `scripts/record-run.mjs` — nothing here is invented.
 * Only the pacing is authored: the recorded run finished faster than a person can read it.
 */

interface ReplayTask {
  id: string;
  role: string;
  description: string;
  summary: string;
  resultHash: string;
  blockNumber: number;
  startAt: number;
  doneAt: number;
  proofAt: number;
}

const TASKS = run.tasks as ReplayTask[];
const LOOP = run.loopSeconds;
const TICK = 0.06;

const ROLE_TEXT: Record<string, string> = {
  researcher: "text-[#5B4BA8]",
  coder: "text-[#12775C]",
  integrator: "text-[#3C5BA8]",
};

function shortHash(hash: string): string {
  return `${hash.slice(0, 16)}…${hash.slice(-4)}`;
}

function grouped(n: number): string {
  return n.toLocaleString("en-GB").replace(/,/g, " ");
}

interface LogLine {
  at: number;
  tag: string;
  text: string;
  tone: string;
}

function buildLog(): LogLine[] {
  const lines: LogLine[] = [
    { at: 0.2, tag: "[goal]", text: "submitted · POST /api/goals", tone: "text-accent" },
    { at: 1.0, tag: "[goal]", text: "status → PLANNING", tone: "text-accent" },
    { at: 2.0, tag: "[plan]", text: `validated · ${TASKS.length} tasks · ${TASKS.length - 1} edges`, tone: "text-accent" },
  ];
  for (const t of TASKS) {
    lines.push({ at: t.startAt, tag: `[${t.role}]`, text: "RUNNING", tone: "text-[#3C5BA8]" });
    lines.push({ at: t.doneAt, tag: "[done]", text: `${t.role} completed`, tone: "text-proof-deep" });
    lines.push({
      at: t.proofAt,
      tag: "[proof]",
      text: `hash recorded · block ${grouped(t.blockNumber)}`,
      tone: "text-proof-deep",
    });
  }
  lines.push({ at: 13.2, tag: "[goal]", text: "COMPLETED", tone: "text-proof-deep" });
  return lines;
}

const LOG = buildLog();

/** Settled end-state shown instead of animating when the viewer asks for reduced motion. */
const SETTLED = 13.6;

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function RunReplay() {
  // Seeded lazily so the reduced-motion case never needs a setState inside the effect.
  const [elapsed, setElapsed] = useState(() => (prefersReducedMotion() ? SETTLED : 0));

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const id = window.setInterval(() => {
      setElapsed((e) => (e + TICK) % LOOP);
    }, TICK * 1000);
    return () => window.clearInterval(id);
  }, []);

  const done = TASKS.filter((t) => elapsed >= t.doneAt).length;
  const proofs = TASKS.filter((t) => elapsed >= t.proofAt).length;
  const visible = LOG.filter((l) => elapsed >= l.at).slice(-8);

  let phase = "submitted";
  if (elapsed >= 1.0) phase = "planning";
  if (elapsed >= TASKS[0].startAt) phase = "running";
  if (elapsed >= 13.2) phase = "completed";

  return (
    <div className="aurora-glass overflow-hidden rounded-[30px]">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/[0.07] px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full bg-[#F1EBFF] px-3 py-1.5 text-xs font-semibold text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Replaying a real run
          </span>
          <span className="font-sora text-sm font-bold text-ink">{run.title}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-ink-dim">+{elapsed.toFixed(1)}s</span>
          <span className="rounded-lg bg-ink/[0.05] px-2.5 py-1 font-mono text-[11px] text-ink-muted">{phase}</span>
        </div>
      </div>

      {/* progress */}
      <div className="h-[3px] bg-ink/[0.06]">
        <div
          className="h-[3px] bg-gradient-to-r from-accent to-proof transition-[width] duration-100 ease-linear"
          style={{ width: `${Math.round((elapsed / LOOP) * 100)}%` }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px]">
        {/* task graph */}
        <div className="border-b border-ink/[0.07] px-5 py-5 sm:px-6 lg:border-b-0 lg:border-r">
          <div className="mb-4 flex items-center justify-between">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Task graph</p>
            <span className="font-mono text-[11px] text-ink-dim">
              {done} of {TASKS.length} done
            </span>
          </div>

          <div className="flex flex-col gap-2.5">
            {TASKS.map((task) => {
              const running = elapsed >= task.startAt && elapsed < task.doneAt;
              const finished = elapsed >= task.doneAt;
              const proofed = elapsed >= task.proofAt;
              const border = finished
                ? "border-proof/40 bg-white/85"
                : running
                  ? "border-accent/45 bg-[#F1EBFF]/65"
                  : "border-ink/10 bg-white/50 opacity-60";
              return (
                <div
                  key={task.id}
                  className={`rounded-2xl border p-4 transition-all duration-300 ${border}`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                        finished ? "bg-proof" : running ? "bg-accent" : "bg-ink-dim/50"
                      }`}
                    />
                    <span
                      className={`w-[88px] shrink-0 font-mono text-xs ${
                        finished || running ? ROLE_TEXT[task.role] ?? "text-ink" : "text-ink-dim"
                      }`}
                    >
                      {task.role}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{task.description}</span>
                    <span
                      className={`shrink-0 font-mono text-[11px] ${
                        finished ? "text-proof-deep" : running ? "text-accent" : "text-ink-dim"
                      }`}
                    >
                      {finished ? "done" : running ? "running" : "queued"}
                    </span>
                  </div>

                  {finished && (
                    <div className="mt-3 rounded-xl border border-ink/[0.06] bg-ink/[0.03] px-3.5 py-3 sm:ml-[102px]">
                      <p className="text-xs leading-relaxed text-ink-muted">{task.summary}</p>
                    </div>
                  )}

                  {proofed && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-2.5 sm:ml-[102px]">
                      <span className="rounded-lg bg-[#E9F9F2] px-2.5 py-1 font-mono text-[11px] text-proof-deep">
                        proof minted
                      </span>
                      <span className="font-mono text-[11px] text-ink-muted">{shortHash(task.resultHash)}</span>
                      <span className="font-mono text-[11px] text-ink-dim">block {grouped(task.blockNumber)}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex items-center gap-3 border-t border-ink/[0.07] pt-4">
            <span className="font-mono text-[11px] text-ink-dim">result</span>
            <span className={`text-[13px] ${done === TASKS.length ? "text-ink" : "text-ink-dim"}`}>
              {done === TASKS.length ? run.result : "Agents are working…"}
            </span>
          </div>
        </div>

        {/* event stream */}
        <div className="flex flex-col bg-paper-2/70">
          <div className="flex items-center justify-between px-5 pb-3 pt-4 sm:px-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">Event stream</p>
            <span className="font-mono text-[10px] text-ink-dim">/api/goals/:id/stream</span>
          </div>
          <div className="flex min-h-[240px] flex-col gap-2 px-5 pb-5 sm:px-6">
            {visible.map((line) => (
              <div key={`${line.at}-${line.tag}`} className="flex gap-2 text-[11px] leading-relaxed">
                <span className="shrink-0 font-mono text-ink-dim">+{line.at.toFixed(1)}s</span>
                <span className={`shrink-0 font-mono ${line.tone}`}>{line.tag}</span>
                <span className="break-all font-mono text-ink-muted">{line.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* chain strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink/[0.07] bg-[#E9F9F2]/50 px-5 py-3.5 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-proof-deep">On chain</span>
          <span className="font-mono text-[11px] text-proof-deep">
            {proofs} of {TASKS.length} proofs confirmed
          </span>
        </div>
        <span className="font-mono text-[11px] text-ink-muted">
          ProofOfWork {run.chain.proofOfWork.slice(0, 10)}…{run.chain.proofOfWork.slice(-4)} · {run.chain.name}
        </span>
      </div>
    </div>
  );
}
