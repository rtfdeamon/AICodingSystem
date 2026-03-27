import apiClient from './client';
import type { AuthTokens, User } from '@/types';

export async function login(email: string, password: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>('/auth/login', { email, password });
  return data;
}

export async function register(
  email: string,
  password: string,
  fullName: string,
): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>('/auth/register', {
    email,
    password,
    full_name: fullName,
  });
  return data;
}

export async function refresh(refreshToken: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>('/auth/refresh', {
    refresh_token: refreshToken,
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me');
  return data;
}
