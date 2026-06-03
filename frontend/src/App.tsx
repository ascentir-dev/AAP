import { useState } from "react";
import { Classes } from "@blueprintjs/core";
import { Sidebar } from "./components/Sidebar";
import type { Page } from "./components/Sidebar";
import { DashboardPage } from "./pages/DashboardPage";
import { LeadsPage } from "./pages/LeadsPage";
import { PipelinePage } from "./pages/PipelinePage";
import { CostsPage } from "./pages/CostsPage";
import { SMSDashboardPage } from "./pages/SMSDashboardPage";
import { SMSConversationsPage } from "./pages/SMSConversationsPage";
import { VideoAnalyticsPage } from "./pages/VideoAnalyticsPage";
import { PlaybookPage } from "./pages/PlaybookPage";
import TestingDashboardPage from "./pages/TestingDashboardPage";

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");

  return (
    <div className={`app-layout ${Classes.DARK}`}>
      <Sidebar current={page} onChange={setPage} />
      <main className="main-content">
        {page === "dashboard" && <DashboardPage />}
        {page === "leads" && <LeadsPage />}
        {page === "pipeline" && <PipelinePage />}
        {page === "costs" && <CostsPage />}
        {page === "sms-dashboard" && <SMSDashboardPage />}
        {page === "sms-conversations" && <SMSConversationsPage />}
        {page === "video-analytics" && <VideoAnalyticsPage />}
        {page === "testing-dashboard" && <TestingDashboardPage />}
        {page === "playbook" && <PlaybookPage />}
      </main>
    </div>
  );
}
