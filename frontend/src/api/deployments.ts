import apiClient from './client';
import type { Deployment } from '@/types';

/** Matches backend StagingDeployRequest */
export interface StagingDeployPayload {
  branch?: string;
  commit_sha?: string;
}

/** Matches backend ProductionDeployRequest */
export interface ProductionDeployPayload {
  commit_sha: string;
  canary_pct?: number;
}

/** Matches backend HealthResponse */
export interface HealthStatus {
  healthy: boolean;
  error_rate: number;
  latency_p50: number;
  latency_p95: number;
  latency_p99: number;
  uptime_pct: number;
  details?: Record<string, unknown>;
}

/** List deployments for a ticket. Backend: GET /tickets/{ticketId}/deployments */
export async function list(
  ticketId: string,
): Promise<Deployment[]> {
  const { data } = await apiClient.get<Deployment[]>(
    `/tickets/${ticketId}/deployments`,
  );
  return data;
}

export async function deployStaging(
  ticketId: string,
  payload: StagingDeployPayload = {},
): Promise<Deployment> {
  const { data } = await apiClient.post<Deployment>(
    `/tickets/${ticketId}/deploy/staging`,
    payload,
  );
  return data;
}

export async function deployProduction(
  ticketId: string,
  payload: ProductionDeployPayload,
): Promise<Deployment> {
  const { data } = await apiClient.post<Deployment>(
    `/tickets/${ticketId}/deploy/production`,
    payload,
  );
  return data;
}

export async function rollback(
  deploymentId: string,
  payload: { reason: string },
): Promise<Deployment> {
  const { data } = await apiClient.post<Deployment>(
    `/deployments/${deploymentId}/rollback`,
    payload,
  );
  return data;
}

export async function promoteCanary(
  deploymentId: string,
  payload: { new_percentage: number },
): Promise<Deployment> {
  const { data } = await apiClient.post<Deployment>(
    `/deployments/${deploymentId}/promote`,
    payload,
  );
  return data;
}

/** Health check for a specific deployment. Backend: GET /deployments/{deploymentId}/health */
export async function getHealth(deploymentId: string): Promise<HealthStatus> {
  const { data } = await apiClient.get<HealthStatus>(`/deployments/${deploymentId}/health`);
  return data;
}
