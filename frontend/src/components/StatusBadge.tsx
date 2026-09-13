interface Props {
  status: string;
  size?: "sm" | "md";
}

const config: Record<string, { color: string; dot: string; label: string }> = {
  NEW:             { color: "text-gray-400 bg-gray-400/10 border-gray-400/20", dot: "bg-gray-400", label: "New" },
  PLANNING:        { color: "text-blue-400 bg-blue-400/10 border-blue-400/20", dot: "bg-blue-400 animate-pulse", label: "Planning" },
  RUNNING:         { color: "text-blue-400 bg-blue-400/10 border-blue-400/20", dot: "bg-blue-400 animate-pulse-ring", label: "Running" },
  COMPLETED:       { color: "text-green-400 bg-green-400/10 border-green-400/20", dot: "bg-green-400", label: "Done" },
  FAILED:          { color: "text-red-400 bg-red-400/10 border-red-400/20", dot: "bg-red-400", label: "Failed" },
  PENDING:         { color: "text-gray-500 bg-gray-500/10 border-gray-500/20", dot: "bg-gray-500", label: "Pending" },
  READY:           { color: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20", dot: "bg-yellow-400 animate-pulse", label: "Ready" },
  DONE:            { color: "text-green-400 bg-green-400/10 border-green-400/20", dot: "bg-green-400", label: "Done" },
  WAITING_WEBHOOK: { color: "text-amber-400 bg-amber-400/10 border-amber-400/20", dot: "bg-amber-400 animate-pulse", label: "Waiting" },
};

export function StatusBadge({ status, size = "md" }: Props) {
  const c = config[status] ?? { color: "text-gray-400 bg-gray-400/10 border-gray-400/20", dot: "bg-gray-400", label: status };
  const sz = size === "sm" ? "text-xs px-2 py-0.5 gap-1.5" : "text-xs px-2.5 py-1 gap-2";
  return (
    <span className={`inline-flex items-center rounded-full border font-medium tracking-wide ${c.color} ${sz}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
