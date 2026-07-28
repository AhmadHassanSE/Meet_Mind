import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Upload } from "./pages/Upload";
import { Meetings } from "./pages/Meetings";
import { Board } from "./pages/Board";
import { Approvals } from "./pages/Approvals";
import { Graph } from "./pages/Graph";
import { Analytics } from "./pages/Analytics";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/meetings" element={<Meetings />} />
        <Route path="/board" element={<Board />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
