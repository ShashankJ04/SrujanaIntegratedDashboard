import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { theme } from "./theme";
import { DashboardLayout } from "./layouts";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { hasAccess } from "./auth/permissions";
import {
  LandingPage,
  ToolsDashboardPage,
  PreventiveMaintenancePage,
  LifeReportPage,
  ProductionDashboardPage,
  RMVariancePage,
  RMCorrectionPage,
  ReportsPage,
  RunReportPage,
  LoginPage,
  RbacAdminPage,
} from "./pages";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <DashboardLayout>
                      <LandingPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/dashboards/tools"
                element={
                  <ProtectedRoute requiredAccess="tools">
                    <DashboardLayout>
                      <ToolsDashboardPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/preventive-maintenance"
                element={
                  <ProtectedRoute requiredAccess="preventive_maintenance">
                    <DashboardLayout>
                      <PreventiveMaintenancePage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/life-report"
                element={
                  <ProtectedRoute requiredAccess="life_report">
                    <DashboardLayout>
                      <LifeReportPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/production"
                element={
                  <ProtectedRoute requiredAccess="production">
                    <DashboardLayout>
                      <ProductionDashboardPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/rm-variance"
                element={
                  <ProtectedRoute requiredAccess="rm_variance">
                    <DashboardLayout>
                      <RMVariancePage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reports"
                element={
                  <ProtectedRoute requiredAccess="reports">
                    <DashboardLayout>
                      <ReportsPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/rm-correction"
                element={
                  <ProtectedRoute>
                    <DashboardLayout>
                      <RMCorrectionPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reports/run"
                element={
                  <ProtectedRoute requiredAccess="reports">
                    <DashboardLayout>
                      <RunReportPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/rbac"
                element={
                  <ProtectedRoute requireAdmin>
                    <DashboardLayout>
                      <RbacAdminPage />
                    </DashboardLayout>
                  </ProtectedRoute>
                }
              />
            </Routes>
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function ProtectedRoute({
  children,
  requiredAccess,
  requireAdmin,
}: {
  children: React.ReactNode;
  requiredAccess?: Parameters<typeof hasAccess>[1];
  requireAdmin?: boolean;
}) {
  const { user, permissions, loading } = useAuth();

  if (loading) {
    return (
      <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && !user.isAdmin) {
    return <Navigate to="/" replace />;
  }

  if (requiredAccess && !hasAccess(permissions, requiredAccess)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
