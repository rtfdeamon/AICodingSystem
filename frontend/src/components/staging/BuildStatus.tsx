import {
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  Hammer,
  FileSearch,
  TestTube,
  Shield,
  ExternalLink,
  ArrowRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

type StageStatus = 'pending' | 'running' | 'passed' | 'failed' | 'skipped';

export interface BuildStage {
  name: string;
  status: StageStatus;
  duration_seconds?: number;
  log_url?: string;
}

interface BuildStatusProps {
  stages: BuildStage[];
  buildId?: string;
  startedAt?: string;
}

const stageIcons: Record<string, typeof Hammer> = {
  build: Hammer,
  lint: FileSearch,
  test: TestTube,
  security: Shield,
};

const statusConfig: Record<StageStatus, {
  icon: typeof CheckCircle;
  color: string;
  bg: string;
  label: string;
}> = {
  pending: { icon: Clock, color: 'text-gray-400', bg: 'bg-gray-100', label: 'Pending' },
  running: { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-100', label: 'Running' },
  passed: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100', label: 'Passed' },
  failed: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100', label: 'Failed' },
  skipped: { icon: Clock, color: 'text-gray-400', bg: 'bg-gray-50', label: 'Skipped' },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function BuildStatus({ stages, buildId, startedAt: _startedAt }: BuildStatusProps) {
  const allPassed = stages.every((s) => s.status === 'passed' || s.status === 'skipped');
  const hasFailed = stages.some((s) => s.status === 'failed');
  const isRunning = stages.some((s) => s.status === 'running');

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              'flex h-8 w-8 items-center justify-center rounded-lg',
              allPassed ? 'bg-green-100' : hasFailed ? 'bg-red-100' : 'bg-blue-100',
            )}
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
            ) : allPassed ? (
              <CheckCircle className="h-4 w-4 text-green-600" />
            ) : (
              <XCircle className="h-4 w-4 text-red-600" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Build Pipeline</h3>
            {buildId && (
              <p className="text-[10px] text-gray-400 font-mono">#{buildId}</p>
            )}
          </div>
        </div>
        <Badge
          variant={allPassed ? 'success' : hasFailed ? 'danger' : isRunning ? 'primary' : 'default'}
        >
          {allPassed ? 'All Passed' : hasFailed ? 'Failed' : isRunning ? 'Running' : 'Pending'}
        </Badge>
      </div>

      {/* Pipeline stages */}
      <div className="px-5 py-4">
        <div className="flex items-center justify-between">
          {stages.map((stage, idx) => {
            const config = statusConfig[stage.status];
            const StatusIcon = config.icon;
            const StageIcon = stageIcons[stage.name.toLowerCase()] || Hammer;
            const isAnimated = stage.status === 'running';

            return (
              <div key={stage.name} className="flex items-center">
                {/* Stage card */}
                <div
                  className={clsx(
                    'flex flex-col items-center rounded-lg border px-6 py-4 transition-colors min-w-[120px]',
                    stage.status === 'passed' && 'border-green-200 bg-green-50/50',
                    stage.status === 'failed' && 'border-red-200 bg-red-50/50',
                    stage.status === 'running' && 'border-blue-200 bg-blue-50/30',
                    stage.status === 'pending' && 'border-gray-200 bg-white',
                    stage.status === 'skipped' && 'border-gray-200 bg-gray-50 opacity-60',
                  )}
                >
                  <div className={clsx('flex h-10 w-10 items-center justify-center rounded-full', config.bg)}>
                    <StageIcon className={clsx('h-5 w-5', config.color)} />
                  </div>
                  <span className="mt-2 text-xs font-semibold text-gray-900 capitalize">
                    {stage.name}
                  </span>
                  <div className="mt-1 flex items-center gap-1">
                    <StatusIcon
                      className={clsx('h-3 w-3', config.color, isAnimated && 'animate-spin')}
                    />
                    <span className={clsx('text-[10px] font-medium', config.color)}>
                      {config.label}
                    </span>
                  </div>
                  {stage.duration_seconds !== undefined && (
                    <span className="mt-1 text-[10px] text-gray-400">
                      {formatDuration(stage.duration_seconds)}
                    </span>
                  )}
                  {stage.log_url && (
                    <a
                      href={stage.log_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1.5 inline-flex items-center gap-0.5 text-[10px] text-brand-600 hover:text-brand-700"
                    >
                      <ExternalLink className="h-2.5 w-2.5" />
                      Logs
                    </a>
                  )}
                </div>

                {/* Connector arrow */}
                {idx < stages.length - 1 && (
                  <ArrowRight
                    className={clsx(
                      'mx-2 h-4 w-4 shrink-0',
                      stages[idx + 1].status !== 'pending' ? 'text-gray-400' : 'text-gray-200',
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
