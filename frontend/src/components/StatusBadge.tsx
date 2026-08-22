import { Status } from "./ui";

const LABEL: Record<string, string> = {
  NEW: "New",
  PLANNING: "Planning",
  RUNNING: "Running",
  COMPLETED: "Done",
  FAILED: "Failed",
  PENDING: "Pending",
  READY: "Ready",
  DONE: "Done",
  WAITING_WEBHOOK: "Waiting",
};

export function StatusBadge({ status }: { status: string; size?: "sm" | "md" }) {
  return <Status status={status} label={LABEL[status] ?? status.replace(/_/g, " ")} />;
}
