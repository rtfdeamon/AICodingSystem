import type { ColumnName, TicketPriority } from '@/types';

/* ─── Column definitions ─── */
export const COLUMN_NAMES: ColumnName[] = [
  'backlog',
  'ai_planning',
  'plan_review',
  'ai_coding',
  'code_review',
  'staging',
  'staging_verification',
  'production',
];

export const COLUMN_LABELS: Record<ColumnName, string> = {
  backlog: 'Backlog',
  ai_planning: 'AI Planning',
  plan_review: 'Plan Review',
  ai_coding: 'AI Coding',
  code_review: 'Code Review',
  staging: 'Staging',
  staging_verification: 'Staging Verification',
  production: 'Production',
};

export const COLUMN_COLORS: Record<ColumnName, string> = {
  backlog: '#6B7280',
  ai_planning: '#3B82F6',
  plan_review: '#8B5CF6',
  ai_coding: '#F59E0B',
  code_review: '#EC4899',
  staging: '#10B981',
  staging_verification: '#EF4444',
  production: '#22C55E',
};

/* ─── Priority ─── */
export const PRIORITY_COLORS: Record<TicketPriority, string> = {
  P0: 'bg-red-100 text-red-800',
  P1: 'bg-orange-100 text-orange-800',
  P2: 'bg-yellow-100 text-yellow-800',
  P3: 'bg-green-100 text-green-800',
};

export const PRIORITY_LABELS: Record<TicketPriority, string> = {
  P0: 'P0 - Critical',
  P1: 'P1 - High',
  P2: 'P2 - Medium',
  P3: 'P3 - Low',
};

export const PRIORITY_ORDER: Record<TicketPriority, number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
};

/* ─── API routes ─── */
export const API_ROUTES = {
  AUTH_LOGIN: '/auth/login',
  AUTH_REGISTER: '/auth/register',
  AUTH_REFRESH: '/auth/refresh',
  AUTH_ME: '/auth/me',
  TICKETS: '/tickets',
  PROJECTS: '/projects',
  COMMENTS: '/comments',
} as const;

/* ─── WS event names (dot-delimited, matching backend WSEventType) ─── */
export const WS_EVENTS = {
  TICKET_CREATED: 'ticket.created',
  TICKET_UPDATED: 'ticket.updated',
  TICKET_MOVED: 'ticket.moved',
  TICKET_DELETED: 'ticket.deleted',
  COMMENT_ADDED: 'comment.added',
  COMMENT_UPDATED: 'comment.updated',
  COMMENT_DELETED: 'comment.deleted',
  AI_STATUS: 'ai.status',
  PIPELINE_PROGRESS: 'pipeline.progress',
  REVIEW_REQUESTED: 'review.requested',
  REVIEW_APPROVED: 'review.approved',
  REVIEW_REJECTED: 'review.rejected',
  DEPLOY_STARTED: 'deploy.started',
  DEPLOY_COMPLETED: 'deploy.completed',
  DEPLOY_FAILED: 'deploy.failed',
  NOTIFICATION: 'notification',
} as const;

/* ─── Human gate columns ─── */
export const HUMAN_GATE_COLUMNS: ColumnName[] = ['plan_review', 'code_review'];
