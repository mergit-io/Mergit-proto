/* The four stages of a run, and the one place they are written down. The section
   renders them either as a grid of cards or as a pinned scroll story depending on
   what the visitor's browser and preferences allow, and the two must never drift
   into telling different stories. */
export type RunStage = {
  title: string;
  body: string;
  out: string;
};

export const RUN_STAGES: RunStage[] = [
  {
    title: "You describe an outcome",
    body: "One sentence in plain language. No template to fill in, no workflow to wire up, no step list to keep current.",
    out: "Natural language",
  },
  {
    title: "The orchestrator draws the graph",
    body: "A planning model turns that sentence into a task graph — every node assigned to an agent, with its inputs and dependencies resolved.",
    out: "Task DAG",
  },
  {
    title: "Agents execute in parallel",
    body: "Up to five tasks run at once. Each agent works a tool-call loop against real systems, and every call is checked for idempotency before it fires.",
    out: "Real side effects",
  },
  {
    title: "The work settles",
    body: "The final task returns the result — a pull request, a repository, a report. Each finished task hashes its output and mints a proof on chain.",
    out: "Result and proof",
  },
];
