/** @type {import('tailwindcss').Config} */

// Every colour resolves through a CSS variable so a single class list renders in
// both themes. Adding `dark:` variants to each utility was the alternative and it
// doubles the class list on every element.
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: v("--c-ink"),
        slab: v("--c-slab"),
        raise: v("--c-raise"),
        line: v("--c-line"),
        "line-soft": v("--c-line-soft"),
        text: v("--c-text"),
        dim: v("--c-dim"),
        faint: v("--c-faint"),
        violet: v("--c-violet"),
        "violet-hi": v("--c-violet-hi"),
        "on-violet": v("--c-on-violet"),
        mint: v("--c-mint"),
        amber: v("--c-amber"),
        red: v("--c-red"),
      },
      fontFamily: {
        display: ["Archivo Variable", "Archivo", "Inter", "system-ui", "sans-serif"],
        sans: ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Micro-labels: the eyebrow/column-header voice used across the console.
        micro: ["0.625rem", { lineHeight: "1", letterSpacing: "0.16em" }],
        label: ["0.6875rem", { lineHeight: "1.1", letterSpacing: "0.12em" }],
      },
      letterSpacing: {
        tightest: "-0.045em",
      },
      borderRadius: {
        // The design system is square. Nothing opts back in.
        none: "0",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
