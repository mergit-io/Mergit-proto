import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

/* The editorial header: a hairline, a wordmark, three words of navigation and one
   filled control. Nothing else. The genre's restraint lives mostly in what is
   absent from this bar. */
const LINKS = [
  { href: "#run", label: "The run" },
  { href: "#proof", label: "Proof" },
  { href: "#stack", label: "Stack" },
];

export function NextNav() {
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        stuck ? "border-b border-line bg-ink/85 backdrop-blur-xl" : "border-b border-transparent"
      }`}
    >
      <div className="mx-auto flex h-20 max-w-[1320px] items-center gap-10 px-8">
        <Link to="/next" className="group flex shrink-0 items-center gap-2.5" aria-label="Mergit">
          <span className="h-3 w-3 bg-violet transition-colors group-hover:bg-violet-hi" />
          <span className="font-display text-[15px] font-bold uppercase tracking-tight">Mergit</span>
        </Link>

        <nav className="hidden items-center gap-9 md:flex" aria-label="Sections">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-sm text-dim transition-colors duration-200 hover:text-text"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-6">
          <Link to="/" className="hidden text-sm text-dim transition-colors hover:text-text sm:inline">
            The other one
          </Link>
          <Link to="/app" className="paper-cta">
            Open console
          </Link>
        </div>
      </div>
    </header>
  );
}
