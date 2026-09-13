import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { GoalDetail } from "./pages/GoalDetail";
import "./index.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/goals/:id" element={<GoalDetail />} />
      </Routes>
    </BrowserRouter>
  );
}
