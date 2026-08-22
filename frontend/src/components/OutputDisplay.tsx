import ReactMarkdown from "react-markdown";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Micro } from "./ui";

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
      mermaid
        .render(id, code)
        .then(({ svg }) => {
          if (!cancelled && ref.current) {
            ref.current.innerHTML = svg;
          }
        })
        .catch((e) => {
          if (!cancelled) setError(String(e));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return <pre className="font-mono text-xs text-dim bg-raise border border-line p-3 overflow-x-auto">{code}</pre>;
  }

  return (
    <div
      ref={ref}
      className="my-4 border border-line bg-raise p-4 overflow-x-auto flex justify-center [&>svg]:max-w-full"
    />
  );
}

// Custom code block renderer — intercepts ```mermaid blocks
function CodeBlock({ className, children }: { className?: string; children?: ReactNode }) {
  const lang = (className ?? "").replace("language-", "");
  const code = String(children ?? "").trim();

  if (lang === "mermaid") {
    return <MermaidDiagram code={code} />;
  }

  return (
    <pre className="font-mono text-xs text-text bg-raise border border-line p-3 overflow-x-auto my-3">
      <code>{code}</code>
    </pre>
  );
}

function Heading({ level, children }: { level: 1 | 2 | 3; children?: ReactNode }) {
  const size = level === 1 ? "text-lg" : level === 2 ? "text-base" : "text-sm";
  const Tag = `h${level}` as "h1" | "h2" | "h3";
  return <Tag className={`font-display font-bold ${size} text-text mt-4 mb-2 first:mt-0`}>{children}</Tag>;
}

export function OutputDisplay({ output }: Props) {
  const text = (output.text as string) || (output.summary as string) || (output.output as string);
  const title = (output.title as string) || "";

  return (
    <div className="border-l-2 border-mint border-y border-r border-line bg-slab p-5 space-y-3">
      <div className="flex items-center gap-2 text-mint">
        <span aria-hidden="true">✓</span>
        <Micro>Completed</Micro>
      </div>

      {title && <p className="font-display font-bold text-base text-text">{title}</p>}

      {text ? (
        <div className="text-sm text-text leading-relaxed">
          <ReactMarkdown
            components={{
              h1: ({ children }) => <Heading level={1}>{children}</Heading>,
              h2: ({ children }) => <Heading level={2}>{children}</Heading>,
              h3: ({ children }) => <Heading level={3}>{children}</Heading>,
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noreferrer" className="text-violet hover:underline">
                  {children}
                </a>
              ),
              p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-3">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-3">{children}</ol>,
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-line pl-3 text-dim">{children}</blockquote>
              ),
              code: ({ className, children }) => <CodeBlock className={className}>{children}</CodeBlock>,
            }}
          >
            {text}
          </ReactMarkdown>
        </div>
      ) : (
        <pre className="font-mono text-xs text-text bg-raise border border-line p-3 overflow-x-auto">
          {JSON.stringify(output, null, 2)}
        </pre>
      )}
    </div>
  );
}
