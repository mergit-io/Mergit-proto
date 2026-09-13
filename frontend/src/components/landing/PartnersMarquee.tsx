import { motion } from "framer-motion";

const PARTNERS = [
  { name: "Anthropic",   abbr: "Anthropic" },
  { name: "Groq",        abbr: "Groq" },
  { name: "Tavily",      abbr: "Tavily" },
  { name: "LiteLLM",    abbr: "LiteLLM" },
  { name: "FastAPI",     abbr: "FastAPI" },
  { name: "React Flow",  abbr: "ReactFlow" },
  { name: "Framer",      abbr: "Framer Motion" },
  { name: "SQLite",      abbr: "SQLite" },
];

function PartnerLogo({ abbr }: { name: string; abbr: string }) {
  return (
    <div className="flex items-center gap-2 px-8 py-4 rounded-xl border border-white/5 bg-white/2 mx-4 group cursor-default hover:border-accent/30 hover:bg-accent/5 transition-all duration-300 shrink-0">
      {/* Generic geometric icon placeholder */}
      <div className="w-6 h-6 rounded-md bg-white/10 group-hover:bg-accent/20 transition-colors duration-300 shrink-0" />
      <span className="text-sm font-medium text-white/30 group-hover:text-white/90 transition-colors duration-300 whitespace-nowrap">
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
