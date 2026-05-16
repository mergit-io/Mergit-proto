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
        className={`relative rounded-2xl border transition-all duration-300 ${
          focused
            ? "border-accent/50 shadow-[0_0_0_3px_rgba(0,149,255,0.08),0_0_30px_rgba(0,149,255,0.06)]"
            : "border-white/8 hover:border-white/15"
        }`}
        style={{ background: "rgba(255,255,255,0.025)" }}
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
          className="w-full resize-none bg-transparent px-5 pt-4 pb-14 text-sm text-gray-100 placeholder-text-muted/50 outline-none rounded-2xl leading-relaxed"
        />

        <div className="absolute bottom-3 left-4 right-3 flex items-center justify-between">
          <AnimatePresence mode="wait">
            <motion.span
              key={idx}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="text-xs text-text-muted/50 truncate max-w-[280px]"
            >
              {value.length === 0 ? "⌘ Enter to send" : `${value.length} chars`}
            </motion.span>
          </AnimatePresence>

          <button
            onClick={handleSubmit}
            disabled={!value.trim() || loading}
            className="btn-neon flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-semibold text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200"
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
