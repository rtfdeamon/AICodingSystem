import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/authStore';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { FullPageSpinner } from '@/components/common/Spinner';

// Auth pages
import { LoginPage } from '@/components/auth/LoginPage';
import { RegisterPage } from '@/components/auth/RegisterPage';
import { OAuthCallback } from '@/components/auth/OAuthCallback';

// Layout
import { AppShell } from '@/components/layout/AppShell';

// Protected pages
import { KanbanBoard } from '@/components/kanban/KanbanBoard';
import { TicketDetail } from '@/components/tickets/TicketDetail';
import { MetricsDashboard } from '@/components/dashboard/MetricsDashboard';
import { UserManagement } from '@/components/admin/UserManagement';
import { AboutPage } from '@/components/about/AboutPage';
import { SettingsPage } from '@/components/settings/SettingsPage';

import type { UserRole } from '@/types';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

/* ─── Route guards ─── */

function ProtectedRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);

  if (isLoading) {
    return <FullPageSpinner />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

function RoleRoute({ allowed }: { allowed: UserRole[] }) {
  const user = useAuthStore((s) => s.user);

  if (!user) {
    return <FullPageSpinner />;
  }

  if (!allowed.includes(user.role)) {
    return <Navigate to="/board" replace />;
  }

  return <Outlet />;
}

function PublicOnlyRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (isAuthenticated) {
    return <Navigate to="/board" replace />;
  }

  return <Outlet />;
}

/* ─── App ─── */

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            {/* Public-only routes (redirect if logged in) */}
            <Route element={<PublicOnlyRoute />}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>

            {/* OAuth callback (works regardless of auth state) */}
            <Route path="/auth/callback" element={<OAuthCallback />} />

            {/* Protected routes */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/board" element={<KanbanBoard />} />
                <Route path="/tickets/:id" element={<TicketDetail />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="/settings" element={<SettingsPage />} />

                {/* PM Lead only routes */}
                <Route element={<RoleRoute allowed={['pm_lead']} />}>
                  <Route path="/dashboard" element={<MetricsDashboard />} />
                  <Route path="/admin/users" element={<UserManagement />} />
                </Route>
              </Route>
            </Route>

            {/* Root redirect */}
            <Route path="/" element={<Navigate to="/board" replace />} />
            <Route path="*" element={<Navigate to="/board" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
