import apiClient from './client';
import type { Ticket, PaginatedResponse } from '@/types';

export interface CreateTicketPayload {
  title: string;
  description?: string;
  acceptance_criteria?: string;
  business_task?: string;
  decomposed_task?: string;
  coding_task?: string;
  ai_prompt?: string;
  priority?: Ticket['priority'];
  labels?: string[];
}

export interface UpdateTicketPayload {
  title?: string;
  description?: string;
  acceptance_criteria?: string;
  priority?: Ticket['priority'];
  assignee_id?: string;
  labels?: string[];
  story_points?: number;
}

export interface TicketListParams {
  column_name?: Ticket['column_name'];
  priority?: Ticket['priority'];
  assignee_id?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function createTicket(projectId: string, payload: CreateTicketPayload): Promise<Ticket> {
  const { data } = await apiClient.post<Ticket>(`/projects/${projectId}/tickets`, payload);
  return data;
}

export async function listTickets(
  projectId: string,
  params: TicketListParams = {},
): Promise<PaginatedResponse<Ticket>> {
  const { data } = await apiClient.get<PaginatedResponse<Ticket>>(
    `/projects/${projectId}/tickets`,
    { params },
  );
  return data;
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const { data } = await apiClient.get<Ticket>(`/tickets/${ticketId}`);
  return data;
}

export async function updateTicket(
  ticketId: string,
  payload: UpdateTicketPayload,
): Promise<Ticket> {
  const { data } = await apiClient.patch<Ticket>(`/tickets/${ticketId}`, payload);
  return data;
}

export async function deleteTicket(ticketId: string): Promise<void> {
  await apiClient.delete(`/tickets/${ticketId}`);
}
