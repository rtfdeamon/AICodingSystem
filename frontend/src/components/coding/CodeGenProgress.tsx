import { useEffect, useState } from 'react';
import {
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  RotateCw,
  Bot,
  Zap,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export type SubtaskStatus = 'pending' | 'generating' | 'lint-pass' | 'test-pass' | 'done' | 'failed';

export interface CodeGenSubtask {
  id: string;
  title: string;
  status: SubtaskStatus;
  agent: string;
  retry_count: number;
  started_at?: string;
  finished_at?: string;
}

interface CodeGenProgressProps {
  subtasks: CodeGenSubtask[];
  startedAt?: string;
}

const statusConfig: Record<SubtaskStatus, {
  label: string;
  icon: typeof Clock;
  color: string;
  bgColor: string;
}> = {
  pending: { label: 'Pending', icon: Clock, color: 'text-gray-400', bgColor: 'bg-gray-100' },
  generating: { label: 'Generating', icon: Loader2, color: 'text-blue-600', bgColor: 'bg-blue-100' },
  'lint-pass': { label: 'Lint Pass', icon: CheckCircle, color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  'test-pass': { label: 'Test Pass', icon: CheckCircle, color: 'text-emerald-600', bgColor: 'bg-emerald-100' },
  done: { label: 'Done', icon: CheckCircle, color: 'text-green-600', bgColor: 'bg-green-100' },
  failed: { label: 'Failed', icon: XCircle, color: 'text-red-600', bgColor: 'bg-red-100' },
};

function formatElapsed(startedAt: string): string {
  const seconds = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function CodeGenProgress({ subtasks, startedAt }: CodeGenProgressProps) {
  const [, setTick] = useState(0);

  // Update elapsed time every second
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const completedCount = subtasks.filter((s) => s.status === 'done').length;
  const failedCount = subtasks.filter((s) => s.status === 'failed').length;
  const inProgressCount = subtasks.filter((s) => s.status === 'generating' || s.status === 'lint-pass' || s.status === 'test-pass').length;
  const progressPct = subtasks.length > 0 ? (completedCount / subtasks.length) * 100 : 0;

  return (
    <div className="space-y-4">
      {/* Overall progress */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-brand-600" />
            <h3 className="text-sm font-semibold text-gray-900">Code Generation Progress</h3>
          </div>
          {startedAt && (
            <span className="text-xs text-gray-500">
              Elapsed: <strong className="text-gray-700">{formatElapsed(startedAt)}</strong>
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="relative h-3 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            className={clsx(
              'h-full rounded-full transition-all duration-700',
              failedCount > 0 ? 'bg-gradient-to-r from-brand-600 to-red-500' : 'bg-brand-600',
            )}
            style={{ width: `${progressPct}%` }}
          />
          {inProgressCount > 0 && (
            <div
              className="absolute top-0 h-full rounded-full bg-blue-400 opacity-40 animate-pulse"
              style={{
                left: `${progressPct}%`,
                width: `${(inProgressCount / subtasks.length) * 100}%`,
              }}
            />
          )}
        </div>

        {/* Summary counters */}
        <div className="mt-3 flex items-center gap-4 text-xs">
          <span className="text-green-600 font-medium">{completedCount} done</span>
          <span className="text-blue-600 font-medium">{inProgressCount} in progress</span>
          {failedCount > 0 && (
            <span className="text-red-600 font-medium">{failedCount} failed</span>
          )}
          <span className="text-gray-400">
            {subtasks.length - completedCount - failedCount - inProgressCount} pending
          </span>
        </div>
      </div>

      {/* Per-subtask status list */}
      <div className="space-y-2">
        {subtasks.map((subtask) => {
          const config = statusConfig[subtask.status];
          const StatusIcon = config.icon;
          const isAnimated = subtask.status === 'generating';

          return (
            <div
              key={subtask.id}
              className={clsx(
                'flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors',
                subtask.status === 'done'
                  ? 'border-green-200 bg-green-50/50'
                  : subtask.status === 'failed'
                    ? 'border-red-200 bg-red-50/50'
                    : subtask.status === 'generating'
                      ? 'border-blue-200 bg-blue-50/30'
                      : 'border-gray-200 bg-white',
              )}
            >
              {/* Status icon */}
              <StatusIcon
                className={clsx(
                  'h-5 w-5 shrink-0',
                  config.color,
                  isAnimated && 'animate-spin',
                )}
              />

              {/* Title */}
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium text-gray-900 truncate block">
                  {subtask.title}
                </span>
                {subtask.started_at && !subtask.finished_at && (
                  <span className="text-[10px] text-gray-400">
                    Running for {formatElapsed(subtask.started_at)}
                  </span>
                )}
              </div>

              {/* Agent badge */}
              <Badge variant="purple" className="shrink-0">
                <Bot className="h-3 w-3 mr-1" />
                {subtask.agent}
              </Badge>

              {/* Status badge */}
              <Badge
                variant={
                  subtask.status === 'done' ? 'success'
                    : subtask.status === 'failed' ? 'danger'
                      : subtask.status === 'generating' ? 'primary'
                        : 'default'
                }
              >
                {config.label}
              </Badge>

              {/* Retry count */}
              {subtask.retry_count > 0 && (
                <span className="flex items-center gap-1 text-xs text-orange-600 shrink-0">
                  <RotateCw className="h-3 w-3" />
                  {subtask.retry_count}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
