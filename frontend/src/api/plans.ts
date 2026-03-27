import apiClient from './client';
import type { AiPlan } from '@/types';

/** List plans for a ticket. Backend: GET /tickets/{ticketId}/plans */
export async function getPlans(ticketId: string): Promise<AiPlan[]> {
  const { data } = await apiClient.get<AiPlan[]>(`/tickets/${ticketId}/plans`);
  return data;
}

/** Get a single plan. Backend: GET /tickets/{ticketId}/plans/{planId}  */
export async function getPlan(ticketId: string, planId: string): Promise<AiPlan> {
  const { data } = await apiClient.get<AiPlan>(`/tickets/${ticketId}/plans/${planId}`);
  return data;
}

/** Approve a plan. Backend: POST /tickets/{ticketId}/plans/{planId}/approve  */
export async function approvePlan(ticketId: string, planId: string): Promise<AiPlan> {
  const { data } = await apiClient.post<AiPlan>(
    `/tickets/${ticketId}/plans/${planId}/approve`,
  );
  return data;
}

/** Reject a plan. Backend: POST /tickets/{ticketId}/plans/{planId}/reject  */
export async function rejectPlan(
  ticketId: string,
  planId: string,
  payload: { comment: string },
): Promise<AiPlan> {
  const { data } = await apiClient.post<AiPlan>(
    `/tickets/${ticketId}/plans/${planId}/reject`,
    payload,
  );
  return data;
}
