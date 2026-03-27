import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

export function AppShell() {
  // Connect WebSocket when authenticated
  useWebSocket();

  return (
    <div className="flex h-screen overflow-hidden bg-surface-secondary">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
