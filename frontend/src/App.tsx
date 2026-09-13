import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { Dashboard } from "./pages/Dashboard";
import { GoalDetail } from "./pages/GoalDetail";
import { Models } from "./pages/Models";
import "./index.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Dashboard />} />
        <Route path="/app/goals/:id" element={<GoalDetail />} />
        <Route path="/app/models" element={<Models />} />
      </Routes>
    </BrowserRouter>
  );
}
