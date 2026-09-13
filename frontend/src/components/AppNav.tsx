import { useState } from "react";
import { LayoutDashboard, ExternalLink, Settings } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { ModelSettings } from "./ModelSettings";

export function AppNav() {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-white/6 bg-black/80 backdrop-blur-md">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <button
            onClick={() => nav("/")}
            className="flex items-center gap-2 group"
          >
            <svg viewBox="0 0 32 32" fill="none" className="w-6 h-6">
              <defs>
                <linearGradient id="app-nav-logo" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0095ff" />
                  <stop offset="1" stopColor="#673ae4" />
                </linearGradient>
              </defs>
              <rect x="3" y="3" width="11" height="11" rx="2.5" fill="url(#app-nav-logo)" opacity="0.9" />
              <rect x="18" y="3" width="11" height="11" rx="2.5" fill="url(#app-nav-logo)" opacity="0.5" />
              <rect x="3" y="18" width="11" height="11" rx="2.5" fill="url(#app-nav-logo)" opacity="0.5" />
              <rect x="18" y="18" width="11" height="11" rx="2.5" fill="url(#app-nav-logo)" opacity="0.9" />
            </svg>
            <span className="font-display font-bold text-base text-white tracking-tight">
              omni<span className="text-gradient-blue">Box</span>
            </span>
          </button>

          {/* Nav links */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => nav("/app")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                pathname === "/app"
                  ? "bg-white/8 text-white"
                  : "text-text-muted hover:text-white hover:bg-white/4"
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              Dashboard
            </button>
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-text-muted hover:text-white hover:bg-white/4 transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              API Docs
            </a>
            <button
              onClick={() => setSettingsOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-text-muted hover:text-white hover:bg-white/4 transition-all"
              title="Model Settings"
            >
              <Settings className="w-3.5 h-3.5" />
              Models
            </button>
          </nav>
        </div>
      </header>

      <ModelSettings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}
