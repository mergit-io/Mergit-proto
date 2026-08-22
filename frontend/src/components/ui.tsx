import { Link } from "react-router-dom";
import type { ReactNode } from "react";

/* The shared vocabulary of the console. Every page is assembled from these, so a
   change to a border or a label voice lands everywhere at once. */

// ── Labels ───────────────────────────────────────────────────────────────────

export function Micro({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`micro ${className}`}>{children}</span>;
}

/** Section title: a mono label sitting on the hairline that opens the region. */
export function Eyebrow({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line px-4 py-2.5">
      <Micro>{children}</Micro>
      {right}
    </div>
  );
}

// ── Surfaces ─────────────────────────────────────────────────────────────────

export function Panel({
  title,
  right,
  children,
  className = "",
  bodyClass = "",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && <Eyebrow right={right}>{title}</Eyebrow>}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

/** A sealed block, drawn as an isometric wireframe with the settled task inside.
    The one piece of illustration in the system; it belongs to the proof field. */
export function ProofBlock({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true" fill="none">
      <g stroke="currentColor" strokeWidth="1" opacity="0.55">
        <path d="M60 14 L106 38 L106 82 L60 106 L14 82 L14 38 Z" />
        <path d="M60 14 L60 58 M60 58 L106 38 M60 58 L14 38" />
        <path d="M60 58 L60 106" opacity="0.4" />
      </g>
      <rect x="46" y="46" width="28" height="28" fill="currentColor" />
    </svg>
  );
}

// ── Numbers ──────────────────────────────────────────────────────────────────

/** A single figure with its label beneath. `accent` inverts it into the proof field. */
export function Metric({
  label,
  value,
  accent = false,
  sub,
}: {
  label: string;
  value: ReactNode;
  accent?: boolean;
  sub?: ReactNode;
}) {
  return (
    <div className={`px-5 py-4 ${accent ? "proof-field" : ""}`}>
      <Micro>{label}</Micro>
      <p className="font-display font-bold tabular tracking-tightest text-4xl mt-2 leading-none">
        {value}
      </p>
      {sub && <p className="micro mt-2">{sub}</p>}
    </div>
  );
}

/** Metrics sit shoulder to shoulder sharing one hairline between them. */
export function MetricRow({ children }: { children: ReactNode }) {
  return (
    <div className="panel grid grid-cols-2 md:grid-cols-4 divide-x divide-line">{children}</div>
  );
}

// ── Status ───────────────────────────────────────────────────────────────────

type Tone = "idle" | "run" | "done" | "fail" | "wait";

const TONE: Record<Tone, { dot: string; text: string }> = {
  idle: { dot: "bg-faint", text: "text-dim" },
  run: { dot: "bg-violet animate-blip", text: "text-violet" },
  done: { dot: "bg-mint", text: "text-mint" },
  fail: { dot: "bg-red", text: "text-red" },
  wait: { dot: "bg-amber", text: "text-amber" },
};

export function toneOf(status: string): Tone {
  const s = (status || "").toUpperCase();
  if (["COMPLETED", "DONE", "SUCCESS", "CONFIRMED", "FIXED", "APPROVED"].includes(s)) return "done";
  if (["FAILED", "ERROR", "DENIED", "TAMPERED"].includes(s)) return "fail";
  if (["RUNNING", "PLANNING", "SUBMITTING", "IN_PROGRESS"].includes(s)) return "run";
  if (s.startsWith("WAITING") || ["BLOCKED", "PENDING", "PAUSED"].includes(s)) return "wait";
  return "idle";
}

export function Status({ status, label }: { status: string; label?: string }) {
  const t = TONE[toneOf(status)];
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-micro uppercase ${t.text}`}>
      <span className={`w-1.5 h-1.5 ${t.dot}`} />
      {label ?? status.replace(/_/g, " ")}
    </span>
  );
}

// ── Controls ─────────────────────────────────────────────────────────────────

export function Tabs<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: readonly { id: T; label: string }[];
}) {
  return (
    <div className="flex">
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          className={`px-4 h-9 font-mono text-label uppercase border-b-2 -mb-px transition-colors ${
            value === o.id
              ? "border-violet text-text"
              : "border-transparent text-dim hover:text-text"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Monospace hash, shortened head-and-tail the way a chain explorer shows it. */
export function Hash({ value, chars = 4 }: { value: string | null | undefined; chars?: number }) {
  if (!value) return <span className="font-mono text-dim">—</span>;
  const short =
    value.length > chars * 2 + 4
      ? `${value.slice(0, chars + 2)}…${value.slice(-chars)}`
      : value;
  return (
    <span className="font-mono text-xs tabular" title={value}>
      {short}
    </span>
  );
}

/** How far a proof has got towards the chain, said in the reader's terms rather than the
 *  outbox's. `null` means the proof was minted locally and never queued at all. */
const SETTLEMENT: Record<string, string> = {
  pending: "Queued",
  submitting: "Submitting",
  confirmed: "Settled",
  dead_lettered: "Gave up",
};

export function settlementLabel(status: string | null | undefined): string {
  if (!status) return "Not submitted";
  // Falling back to the raw status keeps a value the backend adds later readable here
  // instead of rendering an empty cell.
  return SETTLEMENT[status] ?? status;
}

// ── States ───────────────────────────────────────────────────────────────────

export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="font-display font-semibold text-lg tracking-tight">{title}</p>
      {children && <p className="text-sm text-dim mt-2 max-w-sm mx-auto leading-relaxed">{children}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="px-6 py-16 flex items-center justify-center gap-3">
      <span className="w-1.5 h-1.5 bg-violet animate-blip" />
      <Micro>{label}</Micro>
    </div>
  );
}

/** Inline notice. Errors state what happened and what to do, never apologise. */
export function Notice({
  tone = "fail",
  children,
  onDismiss,
}: {
  tone?: "fail" | "wait" | "done";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  const border = { fail: "border-red", wait: "border-amber", done: "border-mint" }[tone];
  const text = { fail: "text-red", wait: "text-amber", done: "text-mint" }[tone];
  return (
    <div className={`border-l-2 ${border} border-y border-r border-line bg-slab px-4 py-3 flex items-start gap-3`}>
      <p className={`text-sm flex-1 ${text}`}>{children}</p>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss" className="micro hover:text-text shrink-0">
          ✕
        </button>
      )}
    </div>
  );
}

// ── Layout ───────────────────────────────────────────────────────────────────

/** Page heading: an oversized display line with a mono step marker above it. */
export function PageHead({
  marker,
  title,
  children,
  aside,
}: {
  marker: string;
  title: ReactNode;
  children?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
      <div className="max-w-2xl">
        <Micro>{marker}</Micro>
        <h1 className="font-display font-bold tracking-tightest leading-[0.95] mt-3 text-[clamp(2rem,4.5vw,3.25rem)]">
          {title}
        </h1>
        {children && <p className="text-sm text-dim mt-4 max-w-xl leading-relaxed">{children}</p>}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </header>
  );
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="micro hover:text-text inline-flex items-center gap-2 transition-colors">
      ← {children}
    </Link>
  );
}
