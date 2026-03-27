import apiClient from './client';

/** Backend notification shape — matches backend NotificationResponse */
export interface BackendNotification {
  id: string;
  user_id: string;
  ticket_id?: string;
  channel: string;
  title: string;
  body: string;
  is_read: boolean;
  sent_at: string;
}

export interface NotificationListResponse {
  items: BackendNotification[];
  total: number;
  page: number;
  per_page: number;
}

export interface NotificationListParams {
  page?: number;
  per_page?: number;
  unread_only?: boolean;
}

/** List notifications. Backend: GET /notifications */
export async function list(
  params: NotificationListParams = {},
): Promise<NotificationListResponse> {
  const { data } = await apiClient.get<NotificationListResponse>('/notifications', { params });
  return data;
}

/** Mark a single notification as read. Backend: PATCH /notifications/{id}/read */
export async function markRead(id: string): Promise<BackendNotification> {
  const { data } = await apiClient.patch<BackendNotification>(`/notifications/${id}/read`);
  return data;
}

/** Mark all notifications as read. Backend: POST /notifications/read-all */
export async function markAllRead(): Promise<{ marked_read: number }> {
  const { data } = await apiClient.post<{ marked_read: number }>('/notifications/read-all');
  return data;
}

/** Get unread count. Backend: GET /notifications/unread-count */
export async function unreadCount(): Promise<{ unread_count: number }> {
  const { data } = await apiClient.get<{ unread_count: number }>('/notifications/unread-count');
  return data;
}
