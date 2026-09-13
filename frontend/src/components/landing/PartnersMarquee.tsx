import { motion } from "framer-motion";

const PARTNERS = [
  { name: "Anthropic", abbr: "Anthropic", mark: "A", accent: "#D4A373" },
  { name: "Groq", abbr: "Groq", mark: "GQ", accent: "#F55036" },
  { name: "Tavily", abbr: "Tavily", mark: "TV", accent: "#F97316" },
  { name: "LiteLLM", abbr: "LiteLLM", mark: "LL", accent: "#7C3AED" },
  { name: "FastAPI", abbr: "FastAPI", mark: "FA", accent: "#10B981" },
  { name: "React Flow", abbr: "ReactFlow", mark: "RF", accent: "#61DAFB" },
  { name: "Framer", abbr: "Framer Motion", mark: "FM", accent: "#2563EB" },
  { name: "SQLite", abbr: "SQLite", mark: "DB", accent: "#0F80CC" },
];

type Partner = (typeof PARTNERS)[number];

function PartnerLogo({ abbr, mark, accent }: Partner) {
  return (
    <div
      className="flex items-center gap-3 px-7 py-4 rounded-xl border border-white/10 bg-white/[0.035] mx-4 group cursor-default transition-all duration-300 shrink-0 hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/[0.055]"
      style={{ boxShadow: `0 12px 34px -28px ${accent}` }}
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-xl border bg-black/50 shrink-0 transition-transform duration-300 group-hover:scale-105"
        style={{
          borderColor: `${accent}55`,
          boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.05), 0 0 24px -12px ${accent}`,
        }}
      >
        <span className="text-[10px] font-bold" style={{ color: accent }}>
          {mark}
        </span>
      </div>
      <span className="text-sm font-medium text-white/70 group-hover:text-white transition-colors duration-300 whitespace-nowrap">
        {abbr}
      </span>
    </div>
  );
}

export function PartnersMarquee() {
  const items = [...PARTNERS, ...PARTNERS]; // duplicate for seamless loop

  return (
    <section id="partners" className="relative py-24 overflow-hidden">
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/6 to-transparent" />
      <div className="absolute bottom-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/6 to-transparent" />

      <div className="max-w-6xl mx-auto px-6 mb-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center"
        >
          <p className="text-accent text-sm font-semibold uppercase tracking-widest mb-3">Ecosystem</p>
          <h2 className="font-display font-bold text-gradient mb-4" style={{ fontSize: "clamp(1.8rem, 4vw, 2.8rem)" }}>
            Built on the Best
          </h2>
          <p className="text-text-dim max-w-md mx-auto">
            omniBox is powered by the most trusted infrastructure in the AI ecosystem.
          </p>
        </motion.div>
      </div>

      {/* Edge fades */}
      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-32 h-full bg-gradient-to-r from-black to-transparent z-10 pointer-events-none" />
      <div className="absolute right-0 top-1/2 -translate-y-1/2 w-32 h-full bg-gradient-to-l from-black to-transparent z-10 pointer-events-none" />

      {/* Marquee row 1 */}
      <div className="flex overflow-hidden mb-4">
        <div className="flex animate-marquee" style={{ width: "max-content" }}>
          {items.map((p, i) => (
            <PartnerLogo key={`a-${i}`} {...p} />
          ))}
        </div>
      </div>

      {/* Marquee row 2 (reversed, offset) */}
      <div className="flex overflow-hidden" style={{ direction: "rtl" }}>
        <div className="flex animate-marquee" style={{ width: "max-content", direction: "ltr" }}>
          {[...items].reverse().map((p, i) => (
            <PartnerLogo key={`b-${i}`} {...p} />
          ))}
        </div>
      </div>
    </section>
  );
}
