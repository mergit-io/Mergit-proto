import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Loading } from "./ui";

/**
 * Gate for every /app route.
 *
 * This is presentation only — it decides what to render, not what the user may read. The
 * backend filters every response by owner, so a bypass here shows an empty dashboard
 * rather than someone else's data. That ordering is deliberate: a client-side check that
 * is *load-bearing* is not a check at all.
 *
 * The `VITE_DEMO_MODE` bypass is gone. It defaulted to true in the production image, which
 * meant the deployed build had no login whatsoever — a build flag that could silently
 * switch authentication off is not authentication.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, authConfigured, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loading label="Checking your session" />
      </div>
    );
  }

  // No Google credentials configured: the backend runs single-tenant and reports the
  // caller as a local user. Refusing here would lock an operator out of their own laptop.
  // The backend is the authority on this — it is the side that knows whether login exists.
  if (!authConfigured) {
    return <>{children}</>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
