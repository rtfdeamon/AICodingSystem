import { useEffect } from 'react';
import { useAuthStore } from '@/stores/authStore';

export function useAuth() {
  const store = useAuthStore();
  const { isAuthenticated, user, isLoading, loadUser } = store;

  useEffect(() => {
    if (isAuthenticated && !user && !isLoading) {
      loadUser();
    }
  }, [isAuthenticated, user, isLoading, loadUser]);

  return {
    user: store.user,
    token: store.token,
    isAuthenticated: store.isAuthenticated,
    isLoading: store.isLoading,
    error: store.error,
    login: store.login,
    register: store.register,
    logout: store.logout,
    clearError: store.clearError,
  };
}
