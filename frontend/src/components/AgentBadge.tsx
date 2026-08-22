/* Agents are told apart by a two-letter monogram, not an emoji — the console is
   set in mono and a colour picture in the middle of a data row breaks the line. */
const MARK: Record<string, string> = {
  orchestrator: "OR",
  researcher: "RS",
  writer: "WR",
  coder: "CD",
  integrator: "IN",
};

export function AgentBadge({ agent }: { agent: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-micro uppercase">
      <span className="w-5 h-5 border border-line flex items-center justify-center text-[9px] text-dim shrink-0">
        {MARK[agent] ?? agent.slice(0, 2).toUpperCase()}
      </span>
      {agent}
    </span>
  );
}
