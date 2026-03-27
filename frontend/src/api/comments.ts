import apiClient from './client';
import type { Comment } from '@/types';

export interface CreateCommentPayload {
  ticket_id: string;
  body: string;
  parent_id?: string;
}

export interface UpdateCommentPayload {
  body: string;
}

export async function listComments(ticketId: string): Promise<Comment[]> {
  const { data } = await apiClient.get<Comment[]>(`/tickets/${ticketId}/comments`);
  return data;
}

export async function createComment(payload: CreateCommentPayload): Promise<Comment> {
  const { data } = await apiClient.post<Comment>(
    `/tickets/${payload.ticket_id}/comments`,
    { body: payload.body, parent_id: payload.parent_id },
  );
  return data;
}

export async function updateComment(commentId: string, payload: UpdateCommentPayload): Promise<Comment> {
  const { data } = await apiClient.put<Comment>(`/comments/${commentId}`, payload);
  return data;
}

export async function deleteComment(commentId: string): Promise<void> {
  await apiClient.delete(`/comments/${commentId}`);
}
