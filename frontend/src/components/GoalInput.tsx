import { useRef, useState } from "react";
import { Micro } from "./ui";

/* Starters are real, submittable goals rather than category names: clicking one
   loads it into the field so it can be edited before it is sent. */
const STARTERS = [
  { label: "Audit a repo", text: "Audit mergit-io/Mergit-proto for security issues and open PRs with fixes" },
  { label: "Compare frameworks", text: "Find the top 5 open-source LLM frameworks and write a comparison report" },
  { label: "Fix an issue", text: "Read issue #1 in owner/repo, write the fix, and open a pull request" },
  { label: "Add CI", text: "Add a pytest GitHub Actions workflow to owner/repo and open a PR" },
];

interface Props {
  onSubmit: (goal: string) => void;
  loading?: boolean;
}

export function GoalInput({ onSubmit, loading }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSubmit(trimmed);
    setValue("");
  };

  const load = (text: string) => {
    setValue(text);
    ref.current?.focus();
  };

  return (
    <div>
      <div className="border border-line bg-slab focus-within:border-violet transition-colors">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={3}
          aria-label="Describe the goal to delegate"
          placeholder="Find the top 5 open-source LLM frameworks and write a comparison report…"
          className="w-full resize-none bg-transparent px-4 py-4 text-sm leading-relaxed outline-none"
        />
        <div className="flex items-center justify-between border-t border-line pl-4">
          <Micro>{value.length === 0 ? "⌘ + Enter to send" : `${value.length} characters`}</Micro>
          <button onClick={submit} disabled={!value.trim() || loading} className="btn-primary">
            {loading ? "Delegating…" : "Delegate goal →"}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-px mt-px">
        {STARTERS.map((s) => (
          <button
            key={s.label}
            onClick={() => load(s.text)}
            className="border border-line px-3 h-8 font-mono text-micro uppercase text-dim hover:text-text hover:border-faint transition-colors"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
