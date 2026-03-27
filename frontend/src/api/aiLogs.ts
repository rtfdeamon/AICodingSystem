import apiClient from './client';

/** Backend AI log entry — matches backend AILogEntry */
export interface AILogEntry {
  id: string;
  ticket_id?: string;
  agent: string;
  model: string;
  action: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
  status: string;
  error_message?: string;
  created_at: string;
}

export interface AILogListResponse {
  items: AILogEntry[];
  total: number;
  page: number;
  page_size: number;
}

/** Backend AI stats — matches backend AILogStats */
export interface AILogStats {
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  average_duration_ms: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
}

export interface AiLogListParams {
  ticket_id?: string;
  agent?: string;
  status?: string;
  page?: number;
  per_page?: number;
}

/** List AI logs. Backend: GET /ai-logs */
export async function list(params: AiLogListParams = {}): Promise<AILogListResponse> {
  const { data } = await apiClient.get<AILogListResponse>('/ai-logs', { params });
  return data;
}

/** Get a single AI log entry. Backend: GET /ai-logs/{id} */
export async function getDetail(id: string): Promise<AILogEntry> {
  const { data } = await apiClient.get<AILogEntry>(`/ai-logs/${id}`);
  return data;
}

/** Get AI usage statistics. Backend: GET /ai-logs/stats */
export async function getStats(): Promise<AILogStats> {
  const { data } = await apiClient.get<AILogStats>('/ai-logs/stats');
  return data;
}
