import apiClient from './client';
import type { TestResult } from '@/types';

export interface TestResultDetail extends TestResult {
  report_json?: Record<string, unknown>;
}

export interface TestRunRequest {
  test_type: 'unit' | 'integration' | 'e2e' | 'security';
  branch?: string;
}

export interface TestGenerateRequest {
  target_files?: string[];
  test_type?: 'unit' | 'integration' | 'e2e';
}

export interface TestGenerateResponse {
  ticket_id: string;
  generated_tests: string;
  file_count: number;
  cost_usd: number;
}

/** List test results for a ticket. Backend: GET /tickets/{ticketId}/test-results */
export async function list(
  ticketId: string,
  params: { run_type?: string } = {},
): Promise<TestResult[]> {
  const { data } = await apiClient.get<TestResult[]>(
    `/tickets/${ticketId}/test-results`,
    { params },
  );
  return data;
}

/** Get a single test result with full report. Backend: GET /test-results/{id} */
export async function getDetail(id: string): Promise<TestResultDetail> {
  const { data } = await apiClient.get<TestResultDetail>(`/test-results/${id}`);
  return data;
}

/** Trigger a test run for a ticket. Backend: POST /tickets/{ticketId}/tests/run */
export async function triggerRun(
  ticketId: string,
  payload: TestRunRequest,
): Promise<TestResult> {
  const { data } = await apiClient.post<TestResult>(
    `/tickets/${ticketId}/tests/run`,
    payload,
  );
  return data;
}

/** Trigger AI test generation. Backend: POST /tickets/{ticketId}/tests/generate */
export async function generateAiTests(
  ticketId: string,
  payload: TestGenerateRequest = {},
): Promise<TestGenerateResponse> {
  const { data } = await apiClient.post<TestGenerateResponse>(
    `/tickets/${ticketId}/tests/generate`,
    payload,
  );
  return data;
}
