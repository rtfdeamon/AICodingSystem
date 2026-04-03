/* ─── User ─── */
export type UserRole = 'owner' | 'developer' | 'pm_lead' | 'ai_agent';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  avatar_url?: string;
  is_active: boolean;
  created_at: string;
}

/* ─── Project ─── */
export interface Project {
  id: string;
  name: string;
  description?: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

/* ─── Ticket ─── */
export type TicketPriority = 'P0' | 'P1' | 'P2' | 'P3';

export type ColumnName =
  | 'backlog'
  | 'ai_planning'
  | 'plan_review'
  | 'ai_coding'
  | 'code_review'
  | 'staging'
  | 'staging_verification'
  | 'production';

export interface Ticket {
  id: string;
  project_id: string;
  ticket_number: number;
  title: string;
  description?: string;
  acceptance_criteria?: string;
  business_task?: string;
  decomposed_task?: string;
  coding_task?: string;
  ai_prompt?: string;
  priority: TicketPriority;
  column_name: ColumnName;
  position: number;
  assignee_id?: string;
  assignee?: User;
  reporter_id?: string;
  reporter?: User;
  labels?: string[];
  story_points?: number;
  branch_name?: string;
  pr_url?: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface TicketHistory {
  id: string;
  ticket_id: string;
  user_id?: string;
  user?: User;
  action: string;
  from_column?: ColumnName;
  to_column?: ColumnName;
  details?: string;
  created_at: string;
}

/* ─── Comment ─── */
export interface Comment {
  id: string;
  ticket_id: string;
  user_id: string;
  user?: User;
  parent_id?: string;
  body: string;
  replies?: Comment[];
  created_at: string;
  updated_at: string;
}

/* ─── AI artefacts ─── */
export type AiLogStatus = 'success' | 'error' | 'timeout' | 'fallback';

export interface AiLog {
  id: string;
  ticket_id?: string;
  agent_name: string;
  action_type: string;
  model_id: string;
  prompt_text?: string;
  response_text?: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
  status: AiLogStatus;
  error_message?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export type PlanStatus = 'pending' | 'approved' | 'rejected' | 'superseded';

export interface AiPlan {
  id: string;
  ticket_id: string;
  version: number;
  agent_name: string;
  plan_markdown: string;
  subtasks: Record<string, unknown>[];
  file_list: string[];
  status: PlanStatus;
  review_comment?: string;
  reviewed_by?: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
  created_at: string;
}

export type CodeGenStatus = 'in_progress' | 'completed' | 'failed' | 'retry';

export interface AiCodeGeneration {
  id: string;
  ticket_id: string;
  plan_id: string;
  subtask_index: number;
  agent_name: string;
  branch_name: string;
  files_changed: Record<string, unknown>[];
  commit_sha?: string;
  status: CodeGenStatus;
  retry_count: number;
  lint_passed: boolean;
  test_passed: boolean;
  log_id?: string;
  created_at: string;
}

/* ─── Review ─── */
export type ReviewerType = 'user' | 'ai_agent';
export type ReviewDecision = 'approved' | 'rejected' | 'changes_requested';

export interface Review {
  id: string;
  ticket_id: string;
  reviewer_id?: string;
  reviewer?: User;
  reviewer_type: ReviewerType;
  agent_name?: string;
  decision: ReviewDecision;
  body?: string;
  inline_comments?: Record<string, unknown>[];
  log_id?: string;
  created_at: string;
}

/* ─── Test ─── */
export interface TestResult {
  id: string;
  ticket_id: string;
  run_type: string;
  tool_name: string;
  passed: boolean;
  total_tests: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  coverage_pct?: number;
  report_json?: Record<string, unknown>;
  log_url?: string;
  duration_ms: number;
  created_at: string;
}

/* ─── Deployment ─── */
export type DeployStatus = 'pending' | 'deploying' | 'deployed' | 'rolled_back' | 'failed';
export type DeployType = 'full' | 'canary';

export interface Deployment {
  id: string;
  ticket_id: string;
  environment: 'staging' | 'production';
  deploy_type: DeployType;
  canary_pct?: number;
  status: DeployStatus;
  initiated_by?: string;
  commit_sha?: string;
  build_url?: string;
  health_check?: Record<string, unknown>;
  rollback_reason?: string;
  created_at: string;
  completed_at?: string;
}

/* ─── WebSocket Events ─── */
/* Canonical event types — dot-delimited, matching backend WSEventType */
export type WSEventType =
  | 'ticket.created'
  | 'ticket.updated'
  | 'ticket.moved'
  | 'ticket.deleted'
  | 'comment.added'
  | 'comment.updated'
  | 'comment.deleted'
  | 'ai.status'
  | 'pipeline.progress'
  | 'review.requested'
  | 'review.approved'
  | 'review.rejected'
  | 'deploy.started'
  | 'deploy.completed'
  | 'deploy.failed'
  | 'notification'
  | 'ping'
  | 'pong';

export interface WSEvent<T = unknown> {
  type: WSEventType;
  data: T;
  timestamp: string;
}

/* ─── Notification ─── */
export interface Notification {
  id: string;
  user_id: string;
  ticket_id?: string;
  channel: string;
  title: string;
  body: string;
  is_read: boolean;
  sent_at: string;
}

/* ─── API response wrappers ─── */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiError {
  message: string;
  detail?: string;
  status: number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
