import apiClient from './client';
import type { Review, ReviewDecision } from '@/types';

export interface SubmitReviewPayload {
  decision: ReviewDecision;
  body?: string;
  inline_comments?: {
    file: string;
    line: number;
    comment: string;
    severity: 'critical' | 'warning' | 'suggestion' | 'style';
  }[];
}

export interface AiReviewTriggerResponse {
  review_id: string;
  summary: string;
  comment_count: number;
  total_cost_usd: number;
  agent_reviews: {
    agent_name: string;
    model_id: string;
    summary: string;
    comment_count: number;
    cost_usd: number;
    latency_ms: number;
  }[];
}

/** List all reviews for a ticket. Backend: GET /tickets/{ticketId}/reviews */
export async function getReviews(ticketId: string): Promise<Review[]> {
  const { data } = await apiClient.get<Review[]>(`/tickets/${ticketId}/reviews`);
  return data;
}

/** Submit a human code review for a ticket. Backend: POST /tickets/{ticketId}/reviews */
export async function submitReview(
  ticketId: string,
  payload: SubmitReviewPayload,
): Promise<Review> {
  const { data } = await apiClient.post<Review>(`/tickets/${ticketId}/reviews`, payload);
  return data;
}

/** Trigger AI review for a ticket. Backend: POST /tickets/{ticketId}/reviews/ai-trigger */
export async function triggerAiReview(ticketId: string): Promise<AiReviewTriggerResponse> {
  const { data } = await apiClient.post<AiReviewTriggerResponse>(
    `/tickets/${ticketId}/reviews/ai-trigger`,
  );
  return data;
}
