import type { ReactElement } from "react";

interface Props {
  agent: string;
}

/* Stroke icons rather than emoji: emoji render differently on every platform and are not
   part of this product's visual language. */
const ICONS: Record<string, ReactElement> = {
  researcher: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4.5-4.5" />
    </>
  ),
  writer: (
    <>
      <path d="M5 20h14" />
      <path d="M15.5 4.5l4 4L9 19H5v-4z" />
    </>
  ),
  coder: (
    <>
      <path d="M9 6l-5 6 5 6" />
      <path d="M15 6l5 6-5 6" />
    </>
  ),
  integrator: (
    <>
      <circle cx="7" cy="6" r="2.5" />
      <circle cx="7" cy="18" r="2.5" />
      <circle cx="17" cy="12" r="2.5" />
      <path d="M7 8.5v7M9.5 17l5-3.6M9.5 7l5 3.6" />
    </>
  ),
};

const STYLES: Record<string, string> = {
  researcher: "bg-[#F1EBFF] text-[#5B4BA8]",
  writer: "bg-[#FFF0E7] text-[#B3541F]",
  coder: "bg-[#E9F9F2] text-[#12775C]",
  integrator: "bg-[#EBF1FF] text-[#3C5BA8]",
};

export function AgentBadge({ agent }: Props) {
  const cls = STYLES[agent] ?? "bg-ink/[0.05] text-ink-muted";
  const icon = ICONS[agent] ?? <circle cx="12" cy="12" r="6" />;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[11px] font-medium ${cls}`}>
      <svg
        viewBox="0 0 24 24"
        className="h-3 w-3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        {icon}
      </svg>
      {agent}
    </span>
  );
}
