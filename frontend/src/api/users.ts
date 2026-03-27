/**
 * User management API client.
 */
import apiClient from './client';
import type { User, UserRole } from '@/types';

/** List all active users (pm_lead / owner only). */
export async function listUsers(isActive = true): Promise<User[]> {
  const { data } = await apiClient.get<User[]>('/users', {
    params: { is_active: isActive },
  });
  return data;
}

/** Get a single user by ID. */
export async function getUser(userId: string): Promise<User> {
  const { data } = await apiClient.get<User>(`/users/${userId}`);
  return data;
}

/** Update a user's profile fields. */
export async function updateUser(
  userId: string,
  payload: { full_name?: string; role?: UserRole },
): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${userId}`, payload);
  return data;
}

/** Change a user's role (pm_lead / owner only). */
export async function changeUserRole(
  userId: string,
  role: UserRole,
): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${userId}/role`, { role });
  return data;
}
