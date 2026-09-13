import { motion } from "framer-motion";
import { ArrowRight, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const PLACEHOLDERS = [
  "Research the top AI agent frameworks and summarize findings…",
  "Write a Python script to scrape Hacker News and save results…",
  "Classify this webhook payload and post the result to Slack…",
  "Find competitors for my SaaS product and write a comparison…",
  "Search for recent papers on LLM reasoning and create a report…",
];

interface Props {
  onSubmit: (goal: string) => void;
  loading?: boolean;
}

export function GoalInput({ onSubmit, loading }: Props) {
  const [value, setValue] = useState("");
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIdx((i) => (i + 1) % PLACEHOLDERS.length);
    }, 3500);
    return () => clearInterval(interval);
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
      <div className="relative rounded-2xl border border-border bg-surface focus-within:border-accent/60 focus-within:shadow-[0_0_0_3px_rgba(59,130,246,0.08)] transition-all duration-200">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          rows={3}
          placeholder={PLACEHOLDERS[placeholderIdx]}
          className="w-full resize-none bg-transparent px-4 pt-4 pb-12 text-sm text-gray-100 placeholder-text-muted outline-none rounded-2xl"
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          <span className="text-xs text-text-muted hidden sm:block">⌘ Enter</span>
          <button
            onClick={handleSubmit}
            disabled={!value.trim() || loading}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowRight className="w-3.5 h-3.5" />}
            Delegate
          </button>
        </div>
      </div>
    </motion.div>
  );
}
