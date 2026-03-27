import { create } from 'zustand';
import type { User } from '@/types';
import * as authApi from '@/api/auth';
import {
  setToken,
  setRefreshToken,
  getToken,
  getRefreshToken,
  clearTokens,
} from '@/api/client';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
  loadUser: () => Promise<void>;
  setUser: (user: User) => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: getToken(),
  isAuthenticated: !!getToken(),
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const tokens = await authApi.login(email, password);
      setToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      const user = await authApi.getMe();
      set({
        user,
        token: tokens.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || 'Login failed';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  register: async (email, password, name) => {
    set({ isLoading: true, error: null });
    try {
      const tokens = await authApi.register(email, password, name);
      setToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      const user = await authApi.getMe();
      set({
        user,
        token: tokens.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || 'Registration failed';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  logout: () => {
    clearTokens();
    set({ user: null, token: null, isAuthenticated: false, error: null });
  },

  refreshToken: async () => {
    const refresh = getRefreshToken();
    if (!refresh) {
      get().logout();
      return;
    }
    try {
      const tokens = await authApi.refresh(refresh);
      setToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      set({ token: tokens.access_token, isAuthenticated: true });
    } catch {
      get().logout();
    }
  },

  loadUser: async () => {
    if (!getToken()) return;
    set({ isLoading: true });
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  setUser: (user) => set({ user }),
  clearError: () => set({ error: null }),
}));
