/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:           "#000000",
        "bg-deep":    "#050505",
        surface:      "#111111",
        "surface-2":  "#1b1b1e",
        border:       "#1f1f1f",
        muted:        "#3a3a3a",
        "text-muted": "#6b7280",
        "text-dim":   "#9ca3af",
        accent:       "#0095ff",
        "accent-2":   "#3badff",
        cyan:         "#00d7df",
        purple:       "#673ae4",
        success:      "#22c55e",
        warning:      "#f59e0b",
        danger:       "#ef4444",
      },
      fontFamily: {
        sans:    ["Inter", "system-ui", "sans-serif"],
        display: ["DM Sans", "Inter", "system-ui", "sans-serif"],
        mono:    ["JetBrains Mono", "Fira Code", "monospace"],
      },
      backgroundImage: {
        "gradient-radial":  "radial-gradient(var(--tw-gradient-stops))",
        "hero-glow":        "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(0,149,255,0.25) 0%, transparent 70%)",
        "hero-glow-purple": "radial-gradient(ellipse 60% 50% at 60% 20%, rgba(103,58,228,0.18) 0%, transparent 60%)",
      },
      boxShadow: {
        "neon-blue":    "0 0 20px rgba(0,149,255,0.35), 0 0 60px rgba(0,149,255,0.1)",
        "neon-blue-lg": "0 0 40px rgba(0,149,255,0.5), 0 0 100px rgba(0,149,255,0.15)",
        "glow-purple":  "0 0 30px rgba(103,58,228,0.35)",
        "glass":        "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)",
      },
      backdropBlur: { "4xl": "72px" },
      borderRadius: { "4xl": "2rem", "5xl": "2.5rem" },
    },
  },
  plugins: [],
};
