import { useEffect } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { useWSStore } from '@/stores/wsStore';

/**
 * Connects WebSocket when authenticated and disconnects on logout.
 * Place this once near the top of the authenticated layout.
 */
export function useWebSocket() {
  const token = useAuthStore((s) => s.token);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { connected, reconnecting, connect, disconnect } = useWSStore();

  useEffect(() => {
    if (isAuthenticated && token && !connected) {
      connect(token);
    }

    return () => {
      // Only disconnect on unmount if we own the connection
    };
  }, [isAuthenticated, token, connected, connect]);

  // Disconnect on logout
  useEffect(() => {
    if (!isAuthenticated && connected) {
      disconnect();
    }
  }, [isAuthenticated, connected, disconnect]);

  return { connected, reconnecting };
}
