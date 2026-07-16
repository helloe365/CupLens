import { useState } from "react";

import { AgentChat } from "./pages/AgentChat";
import { Dashboard } from "./pages/Dashboard";
import { Timeline } from "./pages/Timeline";

type View = "dashboard" | "timeline" | "agent";

const views: Array<{ id: View; number: string; label: string }> = [
  { id: "dashboard", number: "01", label: "当前预测" },
  { id: "timeline", number: "02", label: "赛程与变化" },
  { id: "agent", number: "03", label: "Agent 问答" },
];

export default function App() {
  const [view, setView] = useState<View>("dashboard");

  return (
    <div className="app-shell">
      <header className="site-header">
        <button
          className="brand"
          type="button"
          onClick={() => setView("dashboard")}
          aria-label="返回当前预测"
        >
          <span className="brand-mark">C</span>
          <span>
            <strong>CupLens</strong>
            <small>VERIFIED FORECASTS</small>
          </span>
        </button>
        <nav aria-label="主视图">
          {views.map((item) => (
            <button
              aria-current={view === item.id ? "page" : undefined}
              className={view === item.id ? "active" : ""}
              key={item.id}
              onClick={() => setView(item.id)}
              type="button"
            >
              <span>{item.number}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="trust-signal">
          <i />
          PRECOMPUTED
        </div>
      </header>

      <main>
        {view === "dashboard" && <Dashboard />}
        {view === "timeline" && <Timeline />}
        {view === "agent" && <AgentChat />}
      </main>

      <footer>
        <span>CUPLENS / WORLD CUP 2026</span>
        <span>事实与预测严格分层 · 数值来自不可覆盖快照</span>
      </footer>
    </div>
  );
}
