import { motion } from "framer-motion";
import { Code2, X, MessageCircle, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";

const LINKS = {
  Developers: [
    { label: "Documentation", href: "#" },
    { label: "GitHub",        href: "#" },
    { label: "Whitepaper",    href: "#" },
    { label: "API Reference", href: "#" },
  ],
  Company: [
    { label: "About",       href: "#" },
    { label: "Open Roles",  href: "#" },
    { label: "Blog",        href: "#" },
    { label: "Discord",     href: "#" },
  ],
  Legal: [
    { label: "Privacy Policy", href: "#" },
    { label: "Terms of Use",   href: "#" },
    { label: "Cookie Policy",  href: "#" },
  ],
};

const SOCIALS = [
  { Icon: Code2,         href: "#", label: "GitHub" },
  { Icon: X,             href: "#", label: "Twitter" },
  { Icon: MessageCircle, href: "#", label: "Discord" },
];

export function LandingFooter() {
  const nav = useNavigate();

  return (
    <footer id="footer" className="relative overflow-hidden pt-0">
      {/* Grand CTA */}
      <div className="relative min-h-[60vh] flex flex-col items-center justify-center text-center px-6 overflow-hidden">
        {/* Massive glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[500px] rounded-full bg-accent/12 blur-[200px] animate-glow-pulse" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] rounded-full bg-purple/10 blur-[150px] animate-glow-pulse" style={{ animationDelay: "1.5s" }} />
        </div>

        {/* Fade to black at bottom */}
        <div className="absolute bottom-0 inset-x-0 h-48 bg-gradient-to-t from-black to-transparent pointer-events-none z-10" />

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="relative z-20"
        >
          <p className="text-accent text-sm font-semibold uppercase tracking-widest mb-6">
            Ready to delegate?
          </p>
          <h2
            className="font-display font-bold text-gradient leading-[1.02] tracking-tight mb-8"
            style={{ fontSize: "clamp(4rem, 12vw, 10rem)" }}
          >
            Join Us
          </h2>
          <p className="text-text-dim text-lg max-w-md mx-auto mb-10 leading-relaxed">
            The future of AI work is autonomous. Start delegating your first goal today—
            no setup, no workflows, just results.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <button
              onClick={() => nav("/app")}
              className="btn-neon text-white font-semibold px-10 py-4 rounded-full text-base tracking-wide"
            >
              Start for Free →
            </button>
            <a href="#" className="btn-glass text-white font-medium px-10 py-4 rounded-full text-base flex items-center gap-2">
              <Code2 className="w-4 h-4" />
              View on GitHub
            </a>
          </div>
        </motion.div>
      </div>

      {/* Footer grid */}
      <div className="relative z-20 border-t border-white/6 bg-black">
        <div className="max-w-6xl mx-auto px-6 pt-16 pb-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
            {/* Brand column */}
            <div className="md:col-span-1">
              <div className="flex items-center gap-2.5 mb-4">
                <svg viewBox="0 0 32 32" fill="none" className="w-7 h-7">
                  <defs>
                    <linearGradient id="footer-logo" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#0095ff" />
                      <stop offset="1" stopColor="#673ae4" />
                    </linearGradient>
                  </defs>
                  <rect x="3" y="3" width="11" height="11" rx="2.5" fill="url(#footer-logo)" opacity="0.9" />
                  <rect x="18" y="3" width="11" height="11" rx="2.5" fill="url(#footer-logo)" opacity="0.5" />
                  <rect x="3" y="18" width="11" height="11" rx="2.5" fill="url(#footer-logo)" opacity="0.5" />
                  <rect x="18" y="18" width="11" height="11" rx="2.5" fill="url(#footer-logo)" opacity="0.9" />
                </svg>
                <span className="font-display font-bold text-lg text-white tracking-tight">
                  omni<span className="text-gradient-blue">Box</span>
                </span>
              </div>
              <p className="text-text-muted text-sm leading-relaxed max-w-xs">
                The multi-agent platform for autonomous AI work. Delegate any goal, get real results.
              </p>
              <div className="flex items-center gap-3 mt-6">
                {SOCIALS.map(({ Icon, href, label }) => (
                  <a
                    key={label}
                    href={href}
                    aria-label={label}
                    className="w-9 h-9 rounded-lg border border-white/8 bg-white/3 flex items-center justify-center text-text-muted hover:text-white hover:border-white/20 hover:bg-white/6 transition-all duration-200"
                  >
                    <Icon className="w-4 h-4" />
                  </a>
                ))}
              </div>
            </div>

            {/* Link columns */}
            {Object.entries(LINKS).map(([section, links]) => (
              <div key={section}>
                <h4 className="text-xs font-semibold text-white uppercase tracking-widest mb-5">{section}</h4>
                <ul className="space-y-3.5">
                  {links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-text-muted hover:text-white transition-colors duration-200 flex items-center gap-1.5 group"
                      >
                        {link.label}
                        <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-50 transition-opacity" />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Bottom bar */}
          <div className="pt-8 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-xs text-text-muted">
              © {new Date().getFullYear()} omniBox. All rights reserved.
            </p>
            <div className="flex items-center gap-6">
              {["Privacy Policy", "Terms of Use", "Cookie Policy"].map((t) => (
                <a key={t} href="#" className="text-xs text-text-muted hover:text-white/60 transition-colors">
                  {t}
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
