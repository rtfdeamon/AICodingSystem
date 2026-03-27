import type { UserRole, ColumnName } from '@/types';
import { HUMAN_GATE_COLUMNS } from './constants';

/**
 * Whether the column is a human-gated column requiring manual approval.
 */
export function isHumanGateColumn(column: ColumnName): boolean {
  return HUMAN_GATE_COLUMNS.includes(column);
}

/**
 * Check whether a user with the given role can move a ticket between columns.
 * - ai_agent roles cannot move tickets out of human gate columns.
 * - owner and pm_lead can move tickets anywhere.
 * - Developers can move tickets within dev-related columns.
 */
export function canMoveToColumn(
  userRole: UserRole,
  fromColumn: ColumnName,
  toColumn: ColumnName,
): boolean {
  if (userRole === 'owner' || userRole === 'pm_lead') return true;

  // Developers can review plans and code (approve/reject)
  if (userRole === 'developer') {
    // Developer can move from review columns (approve/reject)
    if (fromColumn === 'plan_review' || fromColumn === 'code_review') {
      // But cannot deploy to production — only pm_lead can
      return toColumn !== 'production';
    }
    // Developer cannot deploy to production — only pm_lead can
    if (toColumn === 'production') return false;
    // Developer can move within dev-related columns
    const devColumns: ColumnName[] = [
      'backlog',
      'ai_planning',
      'ai_coding',
      'staging',
      'staging_verification',
    ];
    return devColumns.includes(fromColumn) || devColumns.includes(toColumn);
  }

  // Human gate columns: only owner/pm_lead/developer (handled above)
  if (fromColumn === 'plan_review' || fromColumn === 'code_review') {
    return false;
  }

  // AI agents generally don't move tickets through human gates
  if (userRole === 'ai_agent') {
    const aiColumns: ColumnName[] = [
      'backlog',
      'ai_planning',
      'ai_coding',
      'staging',
    ];
    return aiColumns.includes(fromColumn) && aiColumns.includes(toColumn);
  }

  return false;
}

export function canCreateTicket(userRole: UserRole): boolean {
  return userRole === 'owner' || userRole === 'pm_lead' || userRole === 'developer';
}

export function canDeployToProduction(userRole: UserRole): boolean {
  return userRole === 'pm_lead';
}
