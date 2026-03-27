import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/authStore';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { FullPageSpinner } from '@/components/common/Spinner';

// Layout (kept eager – renders on every authenticated page)
import { AppShell } from '@/components/layout/AppShell';

import type { UserRole } from '@/types';

/* ─── Lazy-loaded route components ─── */

// Auth pages
const LoginPage = lazy(() =>
  import('@/components/auth/LoginPage').then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('@/components/auth/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const OAuthCallback = lazy(() =>
  import('@/components/auth/OAuthCallback').then((m) => ({ default: m.OAuthCallback })),
);

// Protected pages
const KanbanBoard = lazy(() =>
  import('@/components/kanban/KanbanBoard').then((m) => ({ default: m.KanbanBoard })),
);
const TicketDetail = lazy(() =>
  import('@/components/tickets/TicketDetail').then((m) => ({ default: m.TicketDetail })),
);
const MetricsDashboard = lazy(() =>
  import('@/components/dashboard/MetricsDashboard').then((m) => ({ default: m.MetricsDashboard })),
);
const UserManagement = lazy(() =>
  import('@/components/admin/UserManagement').then((m) => ({ default: m.UserManagement })),
);
const AboutPage = lazy(() =>
  import('@/components/about/AboutPage').then((m) => ({ default: m.AboutPage })),
);
const SettingsPage = lazy(() =>
  import('@/components/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);

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

  if (user.role !== 'owner' && !allowed.includes(user.role)) {
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
          <Suspense fallback={<FullPageSpinner />}>
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
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
