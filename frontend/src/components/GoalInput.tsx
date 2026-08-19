import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const PLACEHOLDERS = [
  "Research the GitHub repo owner/repo, find the bug in issue #1, open a PR…",
  "Write and run a Python script to scrape Hacker News top stories…",
  "Find the top 5 open-source LLM frameworks and write a comparison report…",
  "Build a Python CLI tool called jsonstats and ship it as a new GitHub repo…",
  "Search recent LLM reasoning papers and create a structured report…",
];

interface Props {
  onSubmit: (goal: string) => void;
  loading?: boolean;
}

export function GoalInput({ onSubmit, loading }: Props) {
  const [value, setValue] = useState("");
  const [idx, setIdx] = useState(0);
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % PLACEHOLDERS.length), 3500);
    return () => clearInterval(t);
  }, []);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSubmit(trimmed);
    setValue("");
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-2xl mx-auto"
    >
      <div
        className={`relative rounded-[24px] border bg-white transition-all duration-300 ${
          focused
            ? "border-accent/45 shadow-[0_0_0_3px_rgba(109,74,255,0.10),0_34px_64px_-54px_rgba(26,23,37,0.9)]"
            : "border-ink/10 shadow-[0_26px_50px_-50px_rgba(26,23,37,0.9)] hover:border-ink/20"
        }`}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={3}
          placeholder={PLACEHOLDERS[idx]}
          className="w-full resize-none rounded-[24px] bg-transparent px-6 pb-14 pt-5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-dim"
        />

        <div className="absolute bottom-3.5 left-6 right-3.5 flex items-center justify-between">
          <AnimatePresence mode="wait">
            <motion.span
              key={idx}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="max-w-[280px] truncate font-mono text-[11px] text-ink-dim"
            >
              {value.length === 0 ? "⌘ Enter to send" : `${value.length} chars`}
            </motion.span>
          </AnimatePresence>

          <button
            onClick={handleSubmit}
            disabled={!value.trim() || loading}
            className="flex items-center gap-2 rounded-[13px] bg-accent px-5 py-2.5 text-[13px] font-semibold text-white shadow-[0_16px_30px_-18px_rgba(109,74,255,0.95)] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ArrowRight className="w-3.5 h-3.5" />
            )}
            {loading ? "Delegating…" : "Delegate →"}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
