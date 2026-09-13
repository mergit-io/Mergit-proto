import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Wordmark, ThemeToggle } from "../AppNav";

const LINKS = [
  { href: "#run", label: "The run" },
  { href: "#agents", label: "Agents" },
  { href: "#proof", label: "Proof" },
  { href: "#stack", label: "Stack" },
];

export function Navbar() {
  const [stuck, setStuck] = useState(false);
  const [active, setActive] = useState("");

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Which section is being read, so the header says where you are.
  useEffect(() => {
    const sections = LINKS.map((l) => document.querySelector(l.href)).filter(
      (el): el is Element => Boolean(el)
    );
    if (!sections.length) return;

    const io = new IntersectionObserver(
      (entries) => {
        const seen = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (seen?.target.id) setActive(`#${seen.target.id}`);
      },
      // Only the band just under the header counts as "current", so the active
      // link changes once per section instead of flickering between two.
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 }
    );

    sections.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, []);

  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-colors ${
        stuck ? "border-b border-line bg-ink/92 backdrop-blur-md" : "border-b border-transparent"
      }`}
    >
      <div className="max-w-[1400px] mx-auto px-5 h-16 flex items-center gap-6">
        <Wordmark />

        <nav className="hidden md:flex items-center gap-6" aria-label="Sections">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              aria-current={active === l.href ? "true" : undefined}
              className={`relative font-mono text-micro uppercase font-medium transition-colors duration-200 py-1 ${
                active === l.href ? "text-text" : "text-dim hover:text-text"
              }`}
            >
              {l.label}
              <span
                className={`absolute left-0 -bottom-0.5 h-px bg-violet transition-all duration-300 ${
                  active === l.href ? "w-full" : "w-0"
                }`}
              />
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2 ml-auto">
          <a
            href="https://github.com/mergit-io/Mergit-proto"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost hidden sm:inline-flex"
          >
            GitHub
          </a>
          <ThemeToggle />
          <Link to="/app" className="btn-primary">
            Open console →
          </Link>
        </div>
      </div>
    </header>
  );
}
