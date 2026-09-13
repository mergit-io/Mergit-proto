import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { onAuthStateChanged, type User } from "firebase/auth";
import { auth, isAuthConfigured } from "../lib/firebase";

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    if (DEMO_MODE || !auth) return;
    const unsub = onAuthStateChanged(auth, (u) => setUser(u));
    return unsub;
  }, []);

  if (DEMO_MODE) {
    return <>{children}</>;
  }

  // Auth required but no Firebase project configured. Refuse loudly rather than falling
  // through to the app — a misconfiguration must never silently become an open door.
  if (!isAuthConfigured) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-6">
        <div className="max-w-md text-center text-white/70 space-y-2">
          <p className="text-white font-medium">Authentication is not configured</p>
          <p className="text-sm">
            Set the <code className="text-white/90">VITE_FIREBASE_*</code> variables at build
            time, or build with <code className="text-white/90">VITE_DEMO_MODE=true</code> to
            bypass login for a demo.
          </p>
        </div>
      </div>
    );
  }

  // Still waiting for Firebase to resolve auth state
  if (user === undefined) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white animate-spin" />
      </div>
    );
  }

  // Not logged in → send to login page
  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
