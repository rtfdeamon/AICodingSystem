/**
 * Plan API client.
 *
 * NOTE: Backend plan endpoints (list/get/approve/reject) are not yet
 * implemented. These routes are defined here as the target contract
 * for when the backend adds them under /tickets/{ticketId}/plans.
 * See TODO.md blocker #7.
 */
import apiClient from './client';
import type { AiPlan } from '@/types';

/** List plans for a ticket. Backend: GET /tickets/{ticketId}/plans (pending) */
export async function getPlans(ticketId: string): Promise<AiPlan[]> {
  const { data } = await apiClient.get<AiPlan[]>(`/tickets/${ticketId}/plans`);
  return data;
}

/** Get a single plan. Backend: GET /tickets/{ticketId}/plans/{planId} (pending) */
export async function getPlan(ticketId: string, planId: string): Promise<AiPlan> {
  const { data } = await apiClient.get<AiPlan>(`/tickets/${ticketId}/plans/${planId}`);
  return data;
}

/** Approve a plan. Backend: POST /tickets/{ticketId}/plans/{planId}/approve (pending) */
export async function approvePlan(ticketId: string, planId: string): Promise<AiPlan> {
  const { data } = await apiClient.post<AiPlan>(
    `/tickets/${ticketId}/plans/${planId}/approve`,
  );
  return data;
}

/** Reject a plan. Backend: POST /tickets/{ticketId}/plans/{planId}/reject (pending) */
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
