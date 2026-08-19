/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent:       "#6d4aff",
        "accent-2":   "#9c8bff",
        cyan:         "#22d3ee",
        purple:       "#a855f7",

        /* ── Aurora light theme (landing page; /app migrates in a later PR) ── */
        paper:        "#FFFDFB",
        "paper-2":    "#FBFAFF",
        "paper-3":    "#F7F6FB",
        ink:          "#1A1725",
        "ink-2":      "#3A3348",
        "ink-muted":  "#625A73",
        "ink-dim":    "#948BA6",
        "ink-line":   "#E9E6F0",
        warm:         "#FF8A5C",
        proof:        "#10B981",
        "proof-deep": "#0E8F6B",
        success:      "#22c55e",
        warning:      "#f59e0b",
        danger:       "#ef4444",
      },
      fontFamily: {
        sans:    ["Inter", "system-ui", "sans-serif"],
        display: ["DM Sans", "Inter", "system-ui", "sans-serif"],
        mono:    ["JetBrains Mono", "Fira Code", "monospace"],
        /* Aurora pairing — kept separate from `display`/`sans` so /app typography is untouched. */
        sora:    ["Sora", "DM Sans", "system-ui", "sans-serif"],
        manrope: ["Manrope", "Inter", "system-ui", "sans-serif"],
      },
      backdropBlur: { "4xl": "72px" },
      borderRadius: { "4xl": "2rem", "5xl": "2.5rem" },
    },
  },
  plugins: [],
};
