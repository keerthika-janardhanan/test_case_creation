import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { SidebarLayout } from "./app/layouts/SidebarLayout";
import { ProtectedRoute } from "./app/ProtectedRoute";
import { AgenticPage } from "./pages/AgenticPage";
import { RecorderPage } from "./pages/RecorderPage";
import { TestCasesPage } from "./pages/TestCasesPage";
import { ManualTestsPage } from "./pages/ManualTestsPage";
import { TrialRunsPage } from "./pages/TrialRunsPage";
import { GitOpsPage } from "./pages/GitOpsPage";
import { AdminPage } from "./pages/AdminPage";
import { JiraPage } from "./pages/JiraPage";
import { WebsitePage } from "./pages/WebsitePage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { VectorManagePage } from "./pages/VectorManagePage";
import { SettingsPage } from "./pages/SettingsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { VectorSearchPage } from "./pages/VectorSearchPage";

export default function App() {
  return (
    <BrowserRouter>
      <SidebarLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/agentic" replace />} />
          <Route path="/agentic" element={<AgenticPage />} />
          <Route path="/script-generator" element={<AgenticPage />} />
          <Route path="/recorder" element={<RecorderPage />} />
          <Route path="/test-cases" element={<TestCasesPage />} />
          <Route path="/manual-tests" element={<ManualTestsPage />} />
          <Route path="/trial-runs" element={<TrialRunsPage />} />
          <Route path="/vector" element={<VectorSearchPage />} />
          <Route path="/jira" element={<JiraPage />} />
          <Route path="/website" element={<WebsitePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/vector-manage" element={<VectorManagePage />} />
          <Route path="/git" element={<GitOpsPage />} />
          <Route
            path="/admin"
            element={
              <ProtectedRoute roles={["admin"]}>
                <AdminPage />
              </ProtectedRoute>
            }
          />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </SidebarLayout>
    </BrowserRouter>
  );
}
