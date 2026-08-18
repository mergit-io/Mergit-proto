import { createContext, useContext, useEffect, useState } from "react";

/**
 * Who is signed in, and the CSRF token every write must carry.
 *
 * The session itself is an httpOnly cookie the browser attaches on its own — this file
 * never sees it and cannot read it. What it does hold is the CSRF token, which the
 * backend hands out only through `GET /api/auth/me`. That asymmetry is the point: a
 * cross-site page can cause a request to be *sent* with the cookie attached, but it
 * cannot read this response to learn the token, so the write is rejected.
 */

export interface MergitUser {
  id: string;
  email: string;
  name: string;
  picture: string;
  is_admin: boolean;
}

interface AuthState {
  user: MergitUser | null;
  csrfToken: string;
  /** False when the deployment has no Google credentials — local single-tenant mode. */
  authConfigured: boolean;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  csrfToken: "",
  authConfigured: true,
  loading: true,
  refresh: async () => {},
  logout: async () => {},
});

export const useAuth = () => useContext(AuthContext);

/**
 * The CSRF token, readable by the fetch wrapper without threading React context into it.
 *
 * A module-level variable rather than context because `lib/api.ts` is plain functions
 * called from event handlers, not components — and a stale token there is a 403 the user
 * cannot explain.
 */
let currentCsrf = "";
export const getCsrfToken = () => currentCsrf;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<MergitUser | null>(null);
  const [csrfToken, setCsrfToken] = useState("");
  const [authConfigured, setAuthConfigured] = useState(true);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (!res.ok) {
        setUser(null);
        currentCsrf = "";
        setCsrfToken("");
        // A 401 body still tells us whether login is even possible on this deployment.
        try {
          const body = await res.json();
          setAuthConfigured(body.auth_configured !== false);
        } catch {
          setAuthConfigured(true);
        }
        return;
      }
      const body = await res.json();
      setUser(body.user ?? null);
      currentCsrf = body.csrf_token ?? "";
      setCsrfToken(currentCsrf);
      setAuthConfigured(body.auth_configured !== false);
    } catch {
      // A network failure is not a signed-out state — leaving the user signed in and
      // letting the next request fail is less confusing than bouncing them to /login.
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Mergit-CSRF": currentCsrf },
    });
    currentCsrf = "";
    setUser(null);
    window.location.href = "/login";
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, csrfToken, authConfigured, loading, refresh, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}
