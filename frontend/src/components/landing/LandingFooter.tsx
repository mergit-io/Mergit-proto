import { Link } from "react-router-dom";
import { Micro } from "../ui";

const REPO = "https://github.com/mergit-io/Mergit-proto";

/* Every link here resolves to something that exists. A dead "#" in a footer is a
   promise the product cannot keep. */
const COLUMNS = [
  {
    title: "Console",
    links: [
      { label: "Delegate a goal", to: "/app" },
      { label: "Agent economy", to: "/app/economy" },
      { label: "Models", to: "/app/models" },
      { label: "Automate from GitHub", to: "/app/webhooks" },
    ],
  },
  {
    title: "Source",
    links: [
      { label: "Repository", href: REPO },
      { label: "Architecture", href: `${REPO}/blob/main/ARCHITECTURE.md` },
      { label: "How it works", href: `${REPO}/blob/main/EXPLANATION.md` },
      { label: "Roadmap", href: `${REPO}/blob/main/ROADMAP.md` },
    ],
  },
  {
    title: "Reference",
    links: [
      { label: "API docs", href: "/api/docs" },
      { label: "Deployment", href: `${REPO}/blob/main/docs/DEPLOYMENT.md` },
      { label: "Repo map", href: `${REPO}/blob/main/docs/REPO_MAP.md` },
      { label: "Licence", href: `${REPO}/blob/main/LICENSE` },
    ],
  },
];

export function LandingFooter() {
  return (
    <footer id="footer" className="border-t border-line">
      {/* Closing call, stated once, at full size. */}
      <div className="max-w-[1400px] mx-auto px-5 py-20 lg:py-28">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8">
          <div>
            <Micro>Start here</Micro>
            <h2 className="font-display font-bold tracking-tightest leading-[0.95] mt-4 text-[clamp(2rem,5vw,4rem)]">
              Give it something
              <br />
              you keep putting off.
            </h2>
          </div>
          <div className="flex flex-wrap gap-px shrink-0">
            <Link to="/app" className="btn-primary h-11 px-6">
              Delegate a goal →
            </Link>
            <a
              href={REPO}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost h-11 px-6"
            >
              Read the source
            </a>
          </div>
        </div>
      </div>

      <div className="border-t border-line">
        <div className="max-w-[1400px] mx-auto px-5 py-12 grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="w-3.5 h-3.5 bg-violet" />
              <span className="font-display font-bold text-[15px] tracking-tight uppercase">
                Mergit
              </span>
            </div>
            <p className="text-sm text-dim mt-4 max-w-xs leading-relaxed">
              An agent economy where finishing the work mints the proof, and the proof is what
              builds the reputation.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <Micro>{col.title}</Micro>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {"to" in l ? (
                      <Link to={l.to} className="text-sm text-dim hover:text-text transition-colors">
                        {l.label}
                      </Link>
                    ) : (
                      <a
                        href={l.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-dim hover:text-text transition-colors"
                      >
                        {l.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-line">
        <div className="max-w-[1400px] mx-auto px-5 py-5 flex flex-wrap items-center justify-between gap-3">
          <Micro>© 2026 Mergit — prototype</Micro>
          <Micro>The deployed demo runs unauthenticated by design</Micro>
        </div>
      </div>
    </footer>
  );
}
