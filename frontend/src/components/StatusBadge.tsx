interface Props {
  status: string;
  size?: "sm" | "md";
}

const config: Record<string, { color: string; dot: string; label: string }> = {
  NEW:             { color: "bg-ink/[0.05] text-ink-muted",     dot: "bg-ink-dim",              label: "New" },
  PLANNING:        { color: "bg-[#F1EBFF] text-[#5B4BA8]",      dot: "bg-accent animate-pulse", label: "Planning" },
  RUNNING:         { color: "bg-[#F1EBFF] text-[#5B4BA8]",      dot: "bg-accent animate-pulse", label: "Running" },
  COMPLETED:       { color: "bg-[#E9F9F2] text-proof-deep",     dot: "bg-proof",                label: "Done" },
  DONE:            { color: "bg-[#E9F9F2] text-proof-deep",     dot: "bg-proof",                label: "Done" },
  FAILED:          { color: "bg-[#FFF1EF] text-[#C2453B]",      dot: "bg-[#E86A5E]",            label: "Failed" },
  PENDING:         { color: "bg-ink/[0.05] text-ink-dim",       dot: "bg-ink-dim",              label: "Pending" },
  READY:           { color: "bg-[#FFF6E8] text-[#A16207]",      dot: "bg-[#EAB308] animate-pulse", label: "Ready" },
  WAITING_WEBHOOK: { color: "bg-[#FFF6E8] text-[#A16207]",      dot: "bg-[#EAB308] animate-pulse", label: "Waiting" },
};

export function StatusBadge({ status, size = "md" }: Props) {
  const c = config[status] ?? { color: "bg-ink/[0.05] text-ink-muted", dot: "bg-ink-dim", label: status };
  const sz = size === "sm" ? "text-[11px] px-2 py-0.5 gap-1.5" : "text-xs px-2.5 py-1 gap-2";
  return (
    <span className={`inline-flex items-center rounded-full font-semibold ${c.color} ${sz}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
