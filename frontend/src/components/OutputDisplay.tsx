import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";

interface Props {
  output: Record<string, unknown>;
}

export function OutputDisplay({ output }: Props) {
  const text = (output.text as string) || (output.summary as string) || (output.output as string);
  const title = (output.title as string) || "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-success/30 bg-success/5 p-5 space-y-3"
    >
      <div className="flex items-center gap-2">
        <span className="text-green-400">✓</span>
        <h3 className="text-sm font-semibold text-green-400">Completed</h3>
      </div>

      {title && <p className="text-base font-semibold text-gray-100">{title}</p>}

      {text ? (
        <div className="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed">
          <ReactMarkdown>{text}</ReactMarkdown>
        </div>
      ) : (
        <pre className="text-xs text-gray-300 bg-black/30 rounded-lg p-3 overflow-x-auto">
          {JSON.stringify(output, null, 2)}
        </pre>
      )}
    </motion.div>
  );
}
