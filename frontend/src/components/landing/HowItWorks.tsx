import { motion } from "framer-motion";
import { useGlowCard } from "../../hooks/useGlowCard";

const STEPS = [
  {
    n: "01",
    title: "Submit Any Goal",
    desc: "Type a goal in plain English. No templates, no workflows to configure. The system understands intent—research, code, notify, or integrate.",
    tag: "Natural Language → Intention",
  },
  {
    n: "02",
    title: "Watch the Plan Form",
    desc: "Claude reads your goal and emits a task DAG in real time. Watch dependencies resolve, agents get assigned, and the execution graph materialize.",
    tag: "Claude → Task DAG",
  },
  {
    n: "03",
    title: "Agents Execute in Parallel",
    desc: "Specialized agents spin up concurrently. Each one runs its tool-call loop—searching, writing, coding, notifying—fully autonomous.",
    tag: "Multi-Agent → Tools",
  },
  {
    n: "04",
    title: "Results Delivered",
    desc: "The terminal task surfaces the final output. PRs opened, repos created, code artifacts—delivered and verified with full audit trail.",
    tag: "Output → Side-Effects",
  },
];

function StepCard({ step, index }: { step: typeof STEPS[0]; index: number }) {
  const { ref, onMouseMove } = useGlowCard();

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMouseMove}
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.12, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ scale: 1.015 }}
      className="glow-card glass-card rounded-3xl p-8 flex flex-col gap-6 cursor-default transition-transform duration-300"
    >
      {/* Number */}
      <div className="step-number">{step.n}</div>

      {/* Content */}
      <div className="flex flex-col gap-3">
        <h3 className="font-display font-semibold text-white text-xl leading-tight">{step.title}</h3>
        <p className="text-text-dim text-sm leading-relaxed">{step.desc}</p>
      </div>

      {/* Tag */}
      <div className="mt-auto">
        <span className="inline-flex items-center gap-2 text-xs font-mono text-text-muted">
          <span className="w-4 h-px bg-accent/50" />
          {step.tag}
        </span>
      </div>

      {/* Bottom glow line (visible on hover via group) */}
      <div className="absolute bottom-0 left-8 right-8 h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
    </motion.div>
  );
}

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-32 px-6 overflow-hidden">
      {/* Ambient light */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-full bg-accent/4 blur-[200px]" />
      </div>

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <p className="text-accent text-sm font-semibold uppercase tracking-widest mb-3">The Journey</p>
          <h2 className="font-display font-bold text-gradient mb-4" style={{ fontSize: "clamp(2rem, 5vw, 3.5rem)" }}>
            From Goal to Reality
          </h2>
          <p className="text-text-dim max-w-lg mx-auto text-lg leading-relaxed">
            Four steps. Fully autonomous. Zero configuration.
          </p>
        </motion.div>

        {/* Connecting line (desktop) */}
        <div className="hidden lg:block absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-px h-3/4 bg-gradient-to-b from-transparent via-accent/20 to-transparent pointer-events-none" />

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {STEPS.map((step, i) => (
            <StepCard key={step.n} step={step} index={i} />
          ))}
        </div>

        {/* Flow connector */}
        <motion.div
          initial={{ opacity: 0, scaleX: 0 }}
          whileInView={{ opacity: 1, scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.6, duration: 0.8 }}
          className="mt-12 flex items-center justify-center gap-4 text-xs text-text-muted font-mono"
        >
          {["Goal", "→", "Plan", "→", "Execute", "→", "Deliver"].map((token, i) => (
            <span
              key={i}
              className={token === "→" ? "text-accent/40" : "text-text-muted"}
            >
              {token}
            </span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
