import { motion } from "framer-motion";
import { Brain, GitBranch, Hash, Search, Terminal, Zap } from "lucide-react";
import { useGlowCard } from "../../hooks/useGlowCard";

const FADE_UP = {
  hidden: { opacity: 0, y: 32 },
  visible: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] },
  }),
};

/* ── Mini terminal mockup ────────────────────────────────────── */
function TerminalMockup() {
  return (
    <div className="rounded-xl overflow-hidden border border-white/5 font-mono text-xs" style={{ background: "rgba(0,0,0,0.6)" }}>
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-white/5">
        <span className="w-2.5 h-2.5 rounded-full bg-danger/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-warning/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-success/70" />
        <span className="ml-2 text-text-muted">omnibox — agent</span>
      </div>
      <div className="p-4 space-y-2 leading-relaxed">
        <div><span className="text-accent">→</span> <span className="text-text-dim">Goal received:</span> <span className="text-white">"Research top LLM frameworks"</span></div>
        <div><span className="text-purple">›</span> <span className="text-text-dim">Orchestrator planning</span> <span className="text-text-muted">3 tasks</span></div>
        <div><span className="text-success">✓</span> <span className="text-text-dim">researcher:</span> <span className="text-white">web_search(query)</span></div>
        <div><span className="text-success">✓</span> <span className="text-text-dim">writer:</span> <span className="text-white">synthesize → report.md</span></div>
        <div><span className="text-success">✓</span> <span className="text-text-dim">integrator:</span> <span className="text-white">github_pr → PR #42 opened</span></div>
        <div className="flex items-center gap-2 pt-1"><span className="text-accent-2">●</span> <span className="text-accent-2 font-semibold">Goal completed in 28s</span></div>
      </div>
    </div>
  );
}

/* ── Agent grid mockup ───────────────────────────────────────── */
function AgentGridMockup() {
  const agents = [
    { name: "Researcher", color: "text-violet-300 border-violet-500/30 bg-violet-500/10", icon: Search },
    { name: "Writer",     color: "text-sky-300 border-sky-500/30 bg-sky-500/10",         icon: Terminal },
    { name: "Coder",      color: "text-orange-300 border-orange-500/30 bg-orange-500/10", icon: GitBranch },
    { name: "Notifier",   color: "text-green-300 border-green-500/30 bg-green-500/10",    icon: Hash },
  ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {agents.map((a) => (
        <div key={a.name} className={`rounded-xl border p-3 flex items-center gap-2.5 ${a.color}`} style={{ background: "rgba(0,0,0,0.3)" }}>
          <a.icon className="w-4 h-4 shrink-0" />
          <span className="text-xs font-medium">{a.name}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Glow card wrapper ───────────────────────────────────────── */
function GlowCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const { ref, onMouseMove } = useGlowCard();
  return (
    <div ref={ref} onMouseMove={onMouseMove} className={`glow-card glass-card rounded-3xl ${className}`}>
      {children}
    </div>
  );
}

/* ── Section ─────────────────────────────────────────────────── */
export function FeaturesSection() {
  return (
    <section id="features" className="relative py-32 px-6 overflow-hidden">
      {/* Background ambience */}
      <div className="absolute top-1/2 left-1/4 w-[500px] h-[500px] rounded-full bg-purple/5 blur-[160px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] rounded-full bg-accent/5 blur-[140px] pointer-events-none" />

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <p className="text-accent text-sm font-semibold uppercase tracking-widest mb-3">
            What We Built
          </p>
          <h2 className="font-display font-bold text-gradient mb-4" style={{ fontSize: "clamp(2rem, 5vw, 3.5rem)" }}>
            Every layer, purpose-built
          </h2>
          <p className="text-text-dim max-w-xl mx-auto text-lg leading-relaxed">
            From intelligent orchestration to real side-effects—
            omniBox handles the full stack of autonomous AI execution.
          </p>
        </motion.div>

        {/* Bento grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-auto">
          {/* Large card — orchestration */}
          <motion.div
            custom={0} variants={FADE_UP} initial="hidden" whileInView="visible" viewport={{ once: true }}
            className="lg:col-span-2"
          >
            <GlowCard className="p-8 h-full flex flex-col gap-6">
              <div className="flex items-start gap-4">
                <div className="w-11 h-11 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
                  <Brain className="w-5 h-5 text-accent" />
                </div>
                <div>
                  <h3 className="font-display font-semibold text-white text-xl mb-2">Intelligent Orchestration</h3>
                  <p className="text-text-dim text-sm leading-relaxed">
                    Claude decomposes your natural language goal into a precise task DAG.
                    Each node is assigned to the right specialized agent with the right tools—automatically.
                  </p>
                </div>
              </div>
              <div className="mt-auto">
                <TerminalMockup />
              </div>
            </GlowCard>
          </motion.div>

          {/* Tall card — agents */}
          <motion.div
            custom={1} variants={FADE_UP} initial="hidden" whileInView="visible" viewport={{ once: true }}
            className="row-span-2"
          >
            <GlowCard className="p-8 h-full flex flex-col gap-6">
              <div className="w-11 h-11 rounded-xl bg-purple/10 border border-purple/20 flex items-center justify-center">
                <Zap className="w-5 h-5 text-purple" />
              </div>
              <div>
                <h3 className="font-display font-semibold text-white text-xl mb-2">Specialized Agents</h3>
                <p className="text-text-dim text-sm leading-relaxed">
                  Five purpose-built agents—Researcher, Writer, Coder, Notifier, Integrator—each
                  with their own model, tools, and output schema. All running through the same
                  idempotent execution engine.
                </p>
              </div>
              <AgentGridMockup />
              <div className="mt-auto space-y-3">
                {[
                  { label: "Groq 70b", desc: "Researcher, Writer, Coder", color: "bg-violet-500" },
                  { label: "Groq 8b",  desc: "Notifier (fast dispatch)",   color: "bg-sky-500" },
                  { label: "Claude",   desc: "Orchestrator (planning)",     color: "bg-accent" },
                ].map((m) => (
                  <div key={m.label} className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${m.color}`} />
                    <span className="text-xs text-white font-medium w-20 shrink-0">{m.label}</span>
                    <span className="text-xs text-text-muted">{m.desc}</span>
                  </div>
                ))}
              </div>
            </GlowCard>
          </motion.div>

          {/* Card — tools */}
          <motion.div
            custom={2} variants={FADE_UP} initial="hidden" whileInView="visible" viewport={{ once: true }}
          >
            <GlowCard className="p-7 h-full flex flex-col gap-4">
              <div className="w-11 h-11 rounded-xl bg-cyan/10 border border-cyan/20 flex items-center justify-center">
                <Search className="w-5 h-5 text-cyan" />
              </div>
              <h3 className="font-display font-semibold text-white text-lg">Tool-Native Execution</h3>
              <p className="text-text-dim text-sm leading-relaxed">
                Web search, GitHub PRs, code execution—real side-effects
                with full idempotency. Kill the process, restart, tool calls are not re-fired.
              </p>
              <div className="mt-auto flex flex-wrap gap-2">
                {["web_search", "github_pr", "code_exec", "http_request", "file_ops", "github_create_repo"].map((t) => (
                  <span key={t} className="text-xs font-mono px-2.5 py-1 rounded-lg bg-white/4 border border-white/6 text-text-dim">
                    {t}
                  </span>
                ))}
              </div>
            </GlowCard>
          </motion.div>

          {/* Card — reliability */}
          <motion.div
            custom={3} variants={FADE_UP} initial="hidden" whileInView="visible" viewport={{ once: true }}
          >
            <GlowCard className="p-7 h-full flex flex-col gap-4">
              <div className="w-11 h-11 rounded-xl bg-success/10 border border-success/20 flex items-center justify-center">
                <GitBranch className="w-5 h-5 text-success" />
              </div>
              <h3 className="font-display font-semibold text-white text-lg">Always-On Reliability</h3>
              <p className="text-text-dim text-sm leading-relaxed">
                SQLite WAL with atomic lease claiming means tasks resume exactly where they stopped.
                Crash, restart, reconnect—zero data loss, zero duplicate side-effects.
              </p>
              <div className="mt-auto grid grid-cols-3 gap-3">
                {[
                  { label: "Crash", after: "Resume" },
                  { label: "Timeout", after: "Reclaim" },
                  { label: "Retry", after: "Idempotent" },
                ].map((c) => (
                  <div key={c.label} className="rounded-lg border border-white/6 bg-white/2 p-2.5 text-center">
                    <div className="text-xs text-text-muted mb-0.5">{c.label}</div>
                    <div className="text-xs font-semibold text-success">→ {c.after}</div>
                  </div>
                ))}
              </div>
            </GlowCard>
          </motion.div>

          {/* Wide card — real-time visibility */}
          <motion.div
            custom={4} variants={FADE_UP} initial="hidden" whileInView="visible" viewport={{ once: true }}
            className="lg:col-span-3"
          >
            <GlowCard className="p-8 flex flex-col md:flex-row items-center gap-8">
              <div className="flex-1">
                <div className="w-11 h-11 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center mb-5">
                  <Terminal className="w-5 h-5 text-accent" />
                </div>
                <h3 className="font-display font-semibold text-white text-xl mb-3">Real-Time Visibility</h3>
                <p className="text-text-dim text-sm leading-relaxed max-w-md">
                  Watch agents think, plan, and act via live Server-Sent Events. Every tool call,
                  every message, every state transition—streamed to your browser as it happens.
                </p>
              </div>
              <div className="flex-1 rounded-xl border border-white/5 font-mono text-xs overflow-hidden" style={{ background: "rgba(0,0,0,0.5)" }}>
                <div className="px-4 py-2 border-b border-white/5 text-text-muted flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-ring" />
                  Live event stream
                </div>
                <div className="p-4 space-y-1.5 leading-relaxed">
                  {[
                    ["goal_status", "RUNNING", "text-accent"],
                    ["task_update", "[t1] researcher → RUNNING", "text-violet-300"],
                    ["tool_call",   "web_search('LLM frameworks 2026')", "text-yellow-300"],
                    ["tool_result", "web_search → SUCCESS (5 results)", "text-green-400"],
                    ["task_done",   "[t1] output: {summary, sources}", "text-green-400"],
                    ["task_update", "[t2] writer → RUNNING", "text-sky-300"],
                  ].map(([event, msg, color], i) => (
                    <div key={i} className="flex gap-3">
                      <span className="text-text-muted shrink-0">[{String(i + 1).padStart(2, "0")}]</span>
                      <span className={`shrink-0 ${color}`}>{event}</span>
                      <span className="text-gray-400 truncate">{msg}</span>
                    </div>
                  ))}
                </div>
              </div>
            </GlowCard>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
