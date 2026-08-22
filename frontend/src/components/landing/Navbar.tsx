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

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
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
              className="font-mono text-micro uppercase text-dim hover:text-text transition-colors"
            >
              {l.label}
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
