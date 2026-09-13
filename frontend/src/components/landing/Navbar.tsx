import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const NAV_LINKS = [
  { label: "Developers", href: "#features" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Ecosystem", href: "#partners" },
  { label: "About", href: "#footer" },
];

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <motion.header
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="fixed top-0 inset-x-0 z-50 flex justify-center px-6 pt-4"
    >
      <nav
        className="w-full max-w-6xl flex items-center justify-between px-6 py-3 rounded-2xl transition-all duration-500"
        style={{
          background: scrolled
            ? "rgba(0,0,0,0.75)"
            : "rgba(255,255,255,0.02)",
          borderTop: "1px solid rgba(255,255,255,0.08)",
          borderLeft: "1px solid rgba(255,255,255,0.04)",
          borderRight: "1px solid rgba(255,255,255,0.04)",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
        }}
      >
        {/* Logo */}
        <a href="/" className="flex items-center gap-2.5 group">
          <div className="relative w-8 h-8">
            <svg viewBox="0 0 32 32" fill="none" className="w-full h-full">
              <defs>
                <linearGradient id="logo-g" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0095ff" />
                  <stop offset="1" stopColor="#673ae4" />
                </linearGradient>
              </defs>
              <rect x="3" y="3" width="11" height="11" rx="2.5" fill="url(#logo-g)" opacity="0.9" />
              <rect x="18" y="3" width="11" height="11" rx="2.5" fill="url(#logo-g)" opacity="0.5" />
              <rect x="3" y="18" width="11" height="11" rx="2.5" fill="url(#logo-g)" opacity="0.5" />
              <rect x="18" y="18" width="11" height="11" rx="2.5" fill="url(#logo-g)" opacity="0.9" />
            </svg>
            <div className="absolute inset-0 rounded-lg bg-accent/20 blur-md opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
          </div>
          <span className="font-display font-bold text-lg tracking-tight text-white">
            omni<span className="text-gradient-blue">Box</span>
          </span>
        </a>

        {/* Center links */}
        <ul className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <li key={link.label}>
              <a
                href={link.href}
                className="nav-link text-sm text-text-dim hover:text-white transition-colors duration-200 font-medium tracking-wide"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        {/* CTA */}
        <button
          onClick={() => nav("/app")}
          className="btn-neon text-white text-sm font-semibold px-5 py-2.5 rounded-full tracking-wide"
        >
          Launch App →
        </button>
      </nav>
    </motion.header>
  );
}
