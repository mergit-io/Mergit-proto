import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { useEffect, useRef, useState } from "react";

interface Props {
  output: Record<string, unknown>;
}

function MermaidDiagram({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("mermaid").then((m) => {
      const mermaid = m.default;
      mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });
      const id = `mermaid-${Math.random().toString(36).slice(2)}`;
      mermaid.render(id, code).then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
        }
      }).catch((e) => {
        if (!cancelled) setError(String(e));
      });
    });
    return () => { cancelled = true; };
  }, [code]);

  if (error) {
    return (
      <pre className="text-xs text-gray-400 bg-black/30 rounded-lg p-3 overflow-x-auto">
        {code}
      </pre>
    );
  }

  return (
    <div
      ref={ref}
      className="my-4 rounded-xl bg-black/20 p-4 overflow-x-auto flex justify-center [&>svg]:max-w-full"
    />
  );
}

// Custom code block renderer — intercepts ```mermaid blocks
function CodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const lang = (className ?? "").replace("language-", "");
  const code = String(children ?? "").trim();

  if (lang === "mermaid") {
    return <MermaidDiagram code={code} />;
  }

  return (
    <pre className="text-xs text-gray-300 bg-black/30 rounded-lg p-3 overflow-x-auto my-3">
      <code>{code}</code>
    </pre>
  );
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
          <ReactMarkdown
            components={{
              code: ({ className, children }) => (
                <CodeBlock className={className}>{children}</CodeBlock>
              ),
            }}
          >
            {text}
          </ReactMarkdown>
        </div>
      ) : (
        <pre className="text-xs text-gray-300 bg-black/30 rounded-lg p-3 overflow-x-auto">
          {JSON.stringify(output, null, 2)}
        </pre>
      )}
    </motion.div>
  );
}
