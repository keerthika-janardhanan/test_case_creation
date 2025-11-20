import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import DashboardModern from "./pages/DashboardModern";
import LoginPage from "./pages/LoginPage";
import { RecorderPage } from "./pages/RecorderPageNew";
import { ManualTestsPage } from "./pages/ManualTestsPageNew";
import { TestCasesPage } from "./pages/TestCasesPageNew";
import { AgenticPage } from "./pages/AgenticPageNew";
import { 
  TrialRunsPage,
  VectorSearchPage,
  VectorManagePage,
  GitOpsPage,
  JiraPage,
  WebsitePage,
  DocumentsPage,
  SettingsPage
} from "./pages/PlaceholderPages";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { HomePage } from "./components/HomePageNew";
import { HomePageModern } from "./components/HomePageModern";
import { ImmersiveHome } from "./pages/ImmersiveHome";
import { HorizontalFlowLayout } from "./pages/HorizontalFlowLayout";
import { DesignFlow } from "./components/design-flow/DesignFlow";
import { GradientBackground } from "./components/GradientBackground";
import "./App.css";

function App() {
  console.log("App component rendering"); // Debug log
  
  return (
    <div className="App">
      {/* Soft gradient background - like the reference image */}
      <GradientBackground />
      
      <BrowserRouter>
        <Routes>
          {/* Public routes - only accessible when NOT authenticated */}
          <Route 
            path="/login" 
            element={
              <ProtectedRoute requireAuth={false}>
                <LoginPage />
              </ProtectedRoute>
            } 
          />
          
          {/* Test route to check if basic routing works */}
          <Route 
            path="/test" 
            element={
              <div className="min-h-screen flex items-center justify-center bg-gray-900">
                <h1 className="text-5xl font-bold text-white">Test Route Works!</h1>
              </div>
            } 
          />
          
          {/* Main homepage - horizontal flow with all screens */}
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <HorizontalFlowLayout />
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/home" 
            element={
              <ProtectedRoute>
                <HorizontalFlowLayout />
              </ProtectedRoute>
            } 
          />
          
          {/* Alternative immersive home (simple version) */}
          <Route 
            path="/home-simple" 
            element={
              <ProtectedRoute>
                <ImmersiveHome />
              </ProtectedRoute>
            } 
          />
          
          {/* Legacy modern homepage with sidebar */}
          <Route 
            path="/home-modern" 
            element={
              <ProtectedRoute>
                <HomePageModern />
              </ProtectedRoute>
            } 
          />
          
          {/* Legacy animated homepage */}
          <Route 
            path="/home-old" 
            element={
              <ProtectedRoute>
                <HomePage />
              </ProtectedRoute>
            } 
          />
          
          {/* Design flow with parallax */}
          <Route 
            path="/design" 
            element={
              <ProtectedRoute>
                <DesignFlow />
              </ProtectedRoute>
            } 
          />
          
          {/* Execute flow - placeholder for now */}
          <Route 
            path="/execute" 
            element={
              <ProtectedRoute>
                <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-900 via-slate-900 to-black">
                  <h1 className="text-5xl font-bold text-white">Execute Flow - Coming Soon</h1>
                </div>
              </ProtectedRoute>
            } 
          />
          
          {/* Modern Dashboard with shadcn/ui */}
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute>
                <DashboardModern />
              </ProtectedRoute>
            } 
          />
          
          {/* Legacy Dashboard */}
          <Route 
            path="/dashboard-old" 
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } 
          />

          {/* Feature Pages - All existing routes preserved */}
          <Route 
            path="/recorder" 
            element={
              <ProtectedRoute>
                <RecorderPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/manual-tests" 
            element={
              <ProtectedRoute>
                <ManualTestsPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/test-cases" 
            element={
              <ProtectedRoute>
                <TestCasesPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/agentic" 
            element={
              <ProtectedRoute>
                <AgenticPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/trial-runs" 
            element={
              <ProtectedRoute>
                <TrialRunsPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/vector-search" 
            element={
              <ProtectedRoute>
                <VectorSearchPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/vector-manage" 
            element={
              <ProtectedRoute>
                <VectorManagePage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/gitops" 
            element={
              <ProtectedRoute>
                <GitOpsPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/jira" 
            element={
              <ProtectedRoute>
                <JiraPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/website" 
            element={
              <ProtectedRoute>
                <WebsitePage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/documents" 
            element={
              <ProtectedRoute>
                <DocumentsPage />
              </ProtectedRoute>
            } 
          />

          <Route 
            path="/settings" 
            element={
              <ProtectedRoute>
                <SettingsPage />
              </ProtectedRoute>
            } 
          />
          
          {/* Default route - Modern HomePage */}
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <HomePageModern />
              </ProtectedRoute>
            } 
          />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
