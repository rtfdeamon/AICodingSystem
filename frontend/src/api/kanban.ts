import apiClient from './client';
import type { Ticket, ColumnName } from '@/types';

export interface BoardResponse {
  columns: Record<ColumnName, Ticket[]>;
  project_id: string;
}

export interface MoveTicketPayload {
  ticket_id: string;
  to_column: ColumnName;
  comment?: string;
}

export interface ReorderTicketPayload {
  ticket_id: string;
  position: number;
}

export async function getBoard(projectId: string): Promise<BoardResponse> {
  const { data } = await apiClient.get<BoardResponse>(`/projects/${projectId}/board`);
  return data;
}

export async function moveTicket(payload: MoveTicketPayload): Promise<Ticket> {
  const { data } = await apiClient.post<Ticket>(
    `/tickets/${payload.ticket_id}/move`,
    {
      to_column: payload.to_column,
      comment: payload.comment,
    },
  );
  return data;
}

export async function reorderTicket(payload: ReorderTicketPayload): Promise<Ticket> {
  const { data } = await apiClient.patch<Ticket>(
    `/tickets/${payload.ticket_id}/position`,
    { position: payload.position },
  );
  return data;
}
