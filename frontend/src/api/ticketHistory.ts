import apiClient from './client';
import type { TicketHistory } from '@/types';

/** List history entries for a ticket. Backend: GET /tickets/{ticketId}/history */
export async function listHistory(
  ticketId: string,
  params: { page?: number; per_page?: number } = {},
): Promise<TicketHistory[]> {
  const { data } = await apiClient.get<TicketHistory[]>(
    `/tickets/${ticketId}/history`,
    { params },
  );
  return data;
}
