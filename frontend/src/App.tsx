import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { Dashboard } from "./pages/Dashboard";
import { GoalDetail } from "./pages/GoalDetail";
import { Models } from "./pages/Models";
import { Login } from "./pages/Login";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Webhooks } from "./pages/Webhooks";
import { Actions } from "./pages/Actions";
import { Economy } from "./pages/Economy";
import { AgentDetail } from "./pages/AgentDetail";
import { SelfHeal } from "./pages/SelfHeal";
import { Connections } from "./pages/Connections";
import { Approvals } from "./pages/Approvals";
import { NotFound } from "./pages/NotFound";
import { AuthProvider } from "./lib/auth";

/* The landing page. Lazy for the same reason as /next: it is a framed document
   with its own WebGL scene, and the console should not carry a byte of it. */
const KageLanding = lazy(() =>
  import("./pages/KageLanding").then((m) => ({ default: m.KageLanding }))
);
import { ThemeProvider } from "./lib/theme";
import "./index.css";

export default function App() {
  return (
    /* AuthProvider wraps the router so /login can read auth state too: it needs to
       know whether sign-in is even configured, and to bounce an already-signed-in
       user straight to /app. */
    <ThemeProvider>
    <AuthProvider>
      <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <Suspense fallback={<div className="min-h-screen" style={{ background: "#05070a" }} />}>
              <KageLanding />
            </Suspense>
          }
        />
        {/* The moss world it replaced, kept reachable while the two are compared. */}
        <Route path="/moss" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/goals/:id"
          element={
            <ProtectedRoute>
              <GoalDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/models"
          element={
            <ProtectedRoute>
              <Models />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/webhooks"
          element={
            <ProtectedRoute>
              <Webhooks />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/actions"
          element={
            <ProtectedRoute>
              <Actions />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/economy"
          element={
            <ProtectedRoute>
              <Economy />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/economy/agents/:role"
          element={
            <ProtectedRoute>
              <AgentDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/heal"
          element={
            <ProtectedRoute>
              <SelfHeal />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/connections"
          element={
            <ProtectedRoute>
              <Connections />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/approvals"
          element={
            <ProtectedRoute>
              <Approvals />
            </ProtectedRoute>
          }
        />
        {/* Must stay last. Without it an unmatched path rendered an empty document. */}
        <Route path="*" element={<NotFound />} />
      </Routes>
      </BrowserRouter>
    </AuthProvider>
    </ThemeProvider>
  );
}
