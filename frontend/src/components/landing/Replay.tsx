import { useEffect, useState } from "react";
import { Micro } from "../ui";

/* The hero's argument is the run itself: one real goal, decomposed, executed by
   four agents, settled on chain. It replays on a loop rather than being described.

   It lives in its own file because it is now drawn inside the hero's glass panel,
   which is a much smaller and much softer frame than the half-page console panel
   it used to be. `compact` trades the tool name and the progress bar for the two
   lines that carry the meaning, and swaps the console's solid hairlines and mono
   section labels for glass rules and Lexend — everything else about the run is
   identical. */
const STEPS = [
  { agent: "orchestrator", act: "Decomposed the goal into 4 tasks", tool: "plan", ms: 1400 },
  { agent: "researcher", act: "Read the repo and located the flaw", tool: "github_read_file", ms: 2000 },
  { agent: "coder", act: "Wrote the patch and ran it", tool: "code_exec", ms: 2200 },
  { agent: "integrator", act: "Opened pull request #42", tool: "github_pr", ms: 1800 },
];

const GOAL = "Audit mergit-io/proto for security issues and open PRs with fixes";
const RECEIPT = "0x9f2c4b17e8a0…41ab";

function useReplay(count: number, paused: boolean) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStep(count + 1);
      return;
    }
    if (paused) return;
    // `step` runs one past the last row so the settled receipt gets its own beat.
    const delay = step > count ? 3200 : (STEPS[step]?.ms ?? 1200);
    const t = setTimeout(() => setStep((s) => (s > count ? 0 : s + 1)), delay);
    return () => clearTimeout(t);
  }, [step, count, paused]);

  return [step, setStep] as const;
}

export function Replay({ compact = false }: { compact?: boolean }) {
  // Hovering holds the run still so a step can actually be read, and clicking a
  // step jumps to it — the panel is the page's main claim, so it is worth being
  // able to inspect rather than only watch.
  const [paused, setPaused] = useState(false);
  const [step, setStep] = useReplay(STEPS.length, paused);
  const settled = step > STEPS.length;

  // The two voices: Lexend section labels on glass, mono in the console.
  const Label = compact
    ? ({ children }: { children: React.ReactNode }) => (
        <span className="glass-label">{children}</span>
      )
    : Micro;

  const rule = compact ? "rule-glass" : "border-b border-line";
  const ruleSoft = compact ? "rule-glass-soft" : "border-b border-line-soft";

  return (
    <div
      className={compact ? "flex flex-col" : "panel"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      // Focus holds it too — a keyboard user tabbing the steps had no way to stop the
      // run moving under them.
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div
        className={`flex items-center justify-between ${rule} ${compact ? "pb-3" : "px-4 py-2.5"}`}
      >
        <Label>Live run</Label>
        <span className="flex items-center gap-2">
          <span
            className={`w-1.5 h-1.5 transition-colors duration-300 ${
              paused ? "bg-amber" : settled ? "bg-mint" : "bg-violet animate-blip"
            }`}
          />
          <Label>{paused ? "Held" : settled ? "Settled" : "Executing"}</Label>
        </span>
      </div>

      <div className={`${rule} ${compact ? "py-3.5" : "px-4 py-3.5"}`}>
        <Label>Goal</Label>
        <p className={`leading-snug ${compact ? "mt-2 text-[13px]" : "mt-1.5 text-sm"}`}>{GOAL}</p>
      </div>

      <ol className={compact ? "flex-1" : ""}>
        {STEPS.map((s, i) => {
          const done = step > i;
          const active = step === i;
          return (
            <li key={s.agent} className={ruleSoft} aria-current={active ? "step" : undefined}>
              {/* A button may only contain phrasing content, so the row is spans, and
                  the dimming sits on an inner wrapper — on the button it also faded the
                  focus ring, leaving keyboard focus almost invisible on queued steps.
                  No aria-label: it would replace the whole subtree for a screen reader
                  and swallow the status, the tool name and the progress. */}
              <button
                onClick={() => setStep(i)}
                className={`w-full text-left block transition-colors duration-300 ${
                  compact ? "-mx-2 rounded-2xl px-2 py-2.5 hover:bg-white/[0.06]" : "px-4 py-3 hover:bg-raise"
                }`}
              >
                <span
                  className={`block transition-opacity duration-300 ${
                    done || active ? "opacity-100" : "opacity-40"
                  }`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-mono text-micro uppercase text-dim">
                      {String(i + 1).padStart(2, "0")} · {s.agent}
                    </span>
                    <span
                      className={`font-mono text-micro uppercase ${
                        done ? "text-mint" : active ? "text-violet" : "text-faint"
                      }`}
                    >
                      {done ? "Done" : active ? "Running" : "Queued"}
                    </span>
                  </span>
                  <span className={`block ${compact ? "mt-1 text-[13px]" : "mt-1.5 text-sm"}`}>
                    {s.act}
                  </span>
                  {/* The tool call and its bar are the first thing to go in the panel:
                      they are the only rows whose meaning survives being dropped. */}
                  {!compact && (
                    <span className="flex items-center gap-3 mt-2">
                      <code className="font-mono text-micro text-dim">{s.tool}()</code>
                      <span className="flex-1 h-px bg-line relative overflow-hidden">
                        {done && <span className="absolute inset-0 bg-mint" />}
                        {active && <span className="absolute inset-0 bar-indeterminate" />}
                      </span>
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {/* The settled receipt: the moment the run becomes a fact on chain. Inset and
          rounded on glass rather than bled to the panel's edges — a full-bleed bar
          would square off two of the card's corners. */}
      <div
        className={`flex items-center justify-between transition-colors duration-500 ${
          compact
            ? `mt-4 rounded-2xl px-3.5 py-3 ${settled ? "proof-field" : "bg-black/20"}`
            : `px-4 py-3.5 ${settled ? "proof-field" : "bg-slab"}`
        }`}
      >
        <Label>{settled ? "Proof minted" : "Awaiting settlement"}</Label>
        <span
          className={`font-mono tabular ${compact ? "text-[10px]" : "text-xs"} ${
            settled ? "" : "text-faint"
          }`}
        >
          {settled ? RECEIPT : "—"}
        </span>
      </div>
    </div>
  );
}
