import { useEffect, useState } from "react";

import { AgentChat } from "./pages/AgentChat";
import { Dashboard } from "./pages/Dashboard";
import { Evidence } from "./pages/Evidence";
import { Timeline } from "./pages/Timeline";

type View = "dashboard" | "timeline" | "evidence" | "agent";

const views: Array<{ id: View; label: string }> = [
  { id: "dashboard", label: "预测中心" },
  { id: "timeline", label: "淘汰赛" },
  { id: "evidence", label: "模型与证据" },
  { id: "agent", label: "Agent 问答" },
];

function viewFromHash(): View | null {
  const candidate = window.location.hash.replace(/^#\/?/, "") as View;
  return views.some((item) => item.id === candidate) ? candidate : null;
}

export default function App() {
  const [view, setView] = useState<View>(() => viewFromHash() ?? "dashboard");

  function scrollToTop() {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  }

  useEffect(() => {
    const syncView = () => {
      const nextView = viewFromHash();
      if (nextView) setView(nextView);
    };
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  useEffect(() => {
    const current = views.find((item) => item.id === view);
    document.title = `${current?.label ?? "预测中心"} · CupLens`;
    scrollToTop();
  }, [view]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <header className="site-header">
        <a
          className="brand"
          href="#/dashboard"
          aria-label="返回当前预测"
        >
          <span className="brand-mark" aria-hidden="true"><i /></span>
          <span>
            <strong>CupLens</strong>
            <small>2026 VERIFIED FORECAST</small>
          </span>
        </a>
        <nav aria-label="主视图">
          {views.map((item) => (
            <a
              aria-current={view === item.id ? "page" : undefined}
              className={view === item.id ? "active" : ""}
              href={`#/${item.id}`}
              key={item.id}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="header-actions">
          <div className="trust-signal">
            <i />
            SNAPSHOT VERIFIED
          </div>
          <a
            className="header-agent-button"
            href="#/agent"
          >
            问预测 Agent <span aria-hidden="true">↗</span>
          </a>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
        {view === "dashboard" && <Dashboard />}
        {view === "timeline" && <Timeline />}
        {view === "evidence" && <Evidence />}
        {view === "agent" && <AgentChat />}
      </main>

      <footer>
        <div>
          <strong>CupLens</strong>
          <span>WORLD CUP 2026 FORECAST LAB</span>
        </div>
        <p>事实与预测严格分层 · 数值来自不可覆盖快照 · 仅用于技术演示</p>
      </footer>
    </div>
  );
}
