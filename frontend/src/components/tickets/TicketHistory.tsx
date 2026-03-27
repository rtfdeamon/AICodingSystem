import {
  ArrowRight,
  GitBranch,
  Bot,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react';
import type { TicketHistory as TicketHistoryType } from '@/types';
import { Avatar } from '@/components/common/Avatar';
import { Badge } from '@/components/common/Badge';
import { formatColumnName, formatRelativeTime } from '@/utils/formatters';

interface TicketHistoryProps {
  history: TicketHistoryType[];
}

function getIcon(action: string) {
  if (action.includes('move')) return ArrowRight;
  if (action.includes('ai') || action.includes('generate')) return Bot;
  if (action.includes('approve') || action.includes('pass')) return CheckCircle;
  if (action.includes('reject') || action.includes('fail')) return XCircle;
  if (action.includes('create')) return GitBranch;
  return Clock;
}

function getIconColor(action: string) {
  if (action.includes('approve') || action.includes('pass')) return 'text-green-500 bg-green-50';
  if (action.includes('reject') || action.includes('fail')) return 'text-red-500 bg-red-50';
  if (action.includes('ai')) return 'text-brand-500 bg-brand-50';
  if (action.includes('move')) return 'text-blue-500 bg-blue-50';
  return 'text-gray-500 bg-gray-50';
}

export function TicketHistory({ history }: TicketHistoryProps) {
  if (history.length === 0) {
    return (
      <div className="text-center py-12 text-sm text-gray-400">
        No history recorded yet.
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Timeline line */}
      <div className="absolute left-5 top-0 bottom-0 w-px bg-gray-200" />

      <div className="space-y-4">
        {history.map((entry) => {
          const Icon = getIcon(entry.action);
          const iconColor = getIconColor(entry.action);

          return (
            <div key={entry.id} className="relative flex gap-4 pl-0">
              {/* Icon */}
              <div
                className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconColor}`}
              >
                <Icon className="h-4 w-4" />
              </div>

              {/* Content */}
              <div className="flex-1 rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {entry.user ? (
                      <Avatar
                        name={entry.user.full_name}
                        src={entry.user.avatar_url}
                        size="sm"
                      />
                    ) : (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100">
                        <Bot className="h-3 w-3 text-brand-600" />
                      </div>
                    )}
                    <span className="text-sm font-medium text-gray-900">
                      {entry.user?.full_name || 'AI Agent'}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {formatRelativeTime(entry.created_at)}
                  </span>
                </div>

                <p className="mt-1.5 text-sm text-gray-700">{entry.action}</p>

                {entry.from_column && entry.to_column && (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge variant="default">{formatColumnName(entry.from_column)}</Badge>
                    <ArrowRight className="h-3 w-3 text-gray-400" />
                    <Badge variant="primary">{formatColumnName(entry.to_column)}</Badge>
                  </div>
                )}

                {entry.details && (
                  <p className="mt-2 text-xs text-gray-500 bg-gray-50 rounded p-2">
                    {entry.details}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
