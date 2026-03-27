import apiClient from './client';

export interface PipelineStatsResponse {
  tickets_per_column: Record<string, number>;
  avg_time_per_column_hours: Record<string, number>;
  total_tickets: number;
}

export interface AiCostsResponse {
  cost_by_agent: Record<string, number>;
  cost_by_day: Record<string, number>;
  total_cost: number;
  tokens_total: number;
}

export interface CodeQualityResponse {
  lint_pass_rate: number;
  test_coverage_avg: number;
  review_pass_rate: number;
  security_vuln_count: number;
}

export interface DeploymentStatsResponse {
  deploy_count: number;
  rollback_rate: number;
  avg_deploy_time_ms: number;
  success_rate: number;
}

export async function pipelineStats(params?: {
  project_id: string;
}): Promise<PipelineStatsResponse> {
  const { data } = await apiClient.get<PipelineStatsResponse>(
    '/dashboard/pipeline-stats',
    { params },
  );
  return data;
}

export async function aiCosts(params?: {
  project_id: string;
  days?: number;
}): Promise<AiCostsResponse> {
  const { data } = await apiClient.get<AiCostsResponse>('/dashboard/ai-costs', { params });
  return data;
}

export async function codeQuality(params?: {
  project_id: string;
}): Promise<CodeQualityResponse> {
  const { data } = await apiClient.get<CodeQualityResponse>('/dashboard/code-quality', { params });
  return data;
}

export async function deploymentStats(params?: {
  project_id: string;
}): Promise<DeploymentStatsResponse> {
  const { data } = await apiClient.get<DeploymentStatsResponse>('/dashboard/deployment-stats', {
    params,
  });
  return data;
}
