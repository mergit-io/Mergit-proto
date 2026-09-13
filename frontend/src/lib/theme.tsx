import { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "dark" | "light";

const KEY = "mergit-theme";

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "dark",
  toggle: () => {},
});

/* Storage can throw outright — Safari private mode, cookies disabled, embedded webviews.
   This runs in the root provider, so an unguarded throw takes the entire app down rather
   than costing one remembered preference. */
function read(): Theme | null {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

function write(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* the preference simply will not survive a reload */
  }
}

function initial(): Theme {
  return read() ?? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    write(theme);
  }, [theme]);

  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
