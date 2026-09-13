interface Props {
  agent: string;
}

const colors: Record<string, string> = {
  researcher: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  writer:     "bg-sky-500/15 text-sky-300 border-sky-500/30",
  notifier:   "bg-green-500/15 text-green-300 border-green-500/30",
  coder:      "bg-orange-500/15 text-orange-300 border-orange-500/30",
  integrator: "bg-pink-500/15 text-pink-300 border-pink-500/30",
};

const icons: Record<string, string> = {
  researcher: "🔍",
  writer:     "✍️",
  notifier:   "📣",
  coder:      "💻",
  integrator: "🔗",
};

export function AgentBadge({ agent }: Props) {
  const cls = colors[agent] ?? "bg-gray-500/15 text-gray-300 border-gray-500/30";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}>
      <span>{icons[agent] ?? "🤖"}</span>
      {agent}
    </span>
  );
}
