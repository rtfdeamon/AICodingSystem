import { format, formatDistanceToNow, intervalToDuration } from 'date-fns';
import type { TicketPriority, ColumnName } from '@/types';
import { COLUMN_LABELS, PRIORITY_COLORS, PRIORITY_LABELS } from './constants';

export function formatDate(date: string | Date): string {
  return format(new Date(date), 'MMM d, yyyy');
}

export function formatDateTime(date: string | Date): string {
  return format(new Date(date), 'MMM d, yyyy h:mm a');
}

export function formatRelativeTime(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true });
}

export function formatDuration(ms: number): string {
  const duration = intervalToDuration({ start: 0, end: ms });
  const parts: string[] = [];
  if (duration.days) parts.push(`${duration.days}d`);
  if (duration.hours) parts.push(`${duration.hours}h`);
  if (duration.minutes) parts.push(`${duration.minutes}m`);
  if (parts.length === 0) return '< 1m';
  return parts.join(' ');
}

export function formatPriority(priority: TicketPriority): string {
  return PRIORITY_LABELS[priority] ?? priority;
}

export function getPriorityClasses(priority: TicketPriority): string {
  return PRIORITY_COLORS[priority];
}

export function formatColumnName(column: ColumnName): string {
  return COLUMN_LABELS[column];
}

export function truncateText(text: string, maxLength: number = 100): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trimEnd() + '...';
}
