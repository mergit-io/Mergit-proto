import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { onAuthStateChanged, type User } from "firebase/auth";
import { auth } from "../lib/firebase";

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    if (DEMO_MODE) return;
    const unsub = onAuthStateChanged(auth, (u) => setUser(u));
    return unsub;
  }, []);

  if (DEMO_MODE) {
    return <>{children}</>;
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
