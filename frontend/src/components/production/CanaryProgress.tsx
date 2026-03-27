import { useEffect, useState } from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  Activity,
  Gauge,
  AlertTriangle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface CanaryStage {
  percentage: number;
  status: 'pending' | 'active' | 'passed' | 'failed';
  error_rate?: number;
  latency_ms?: number;
  started_at?: string;
  duration_seconds?: number;
}

interface CanaryProgressProps {
  stages: CanaryStage[];
  currentPercentage: number;
}

const STAGE_TARGETS = [5, 25, 50, 100];

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export function CanaryProgress({ stages, currentPercentage }: CanaryProgressProps) {
  const [, setTick] = useState(0);

  // Animate the live timer
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const allPassed = stages.every((s) => s.status === 'passed');
  const hasFailed = stages.some((s) => s.status === 'failed');

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-brand-600" />
          <h3 className="text-sm font-semibold text-gray-900">Canary Deployment</h3>
        </div>
        <Badge
          variant={allPassed ? 'success' : hasFailed ? 'danger' : 'primary'}
          dot
        >
          {allPassed ? 'Complete' : hasFailed ? 'Failed' : `${currentPercentage}% Traffic`}
        </Badge>
      </div>

      {/* Animated progress bar */}
      <div className="relative mb-6">
        <div className="h-4 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            className={clsx(
              'h-full rounded-full transition-all duration-1000 ease-out',
              hasFailed
                ? 'bg-gradient-to-r from-green-500 to-red-500'
                : 'bg-gradient-to-r from-green-500 via-brand-500 to-brand-600',
            )}
            style={{ width: `${currentPercentage}%` }}
          />
        </div>
        {/* Percentage markers */}
        <div className="relative mt-1">
          {STAGE_TARGETS.map((target) => (
            <span
              key={target}
              className="absolute text-[10px] text-gray-400 -translate-x-1/2"
              style={{ left: `${target}%` }}
            >
              {target}%
            </span>
          ))}
        </div>
      </div>

      {/* Stage cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stages.map((stage, idx) => {
          const target = STAGE_TARGETS[idx] ?? stage.percentage;
          const isActive = stage.status === 'active';

          return (
            <div
              key={idx}
              className={clsx(
                'rounded-lg border p-3 transition-all',
                stage.status === 'passed' && 'border-green-200 bg-green-50/50',
                stage.status === 'failed' && 'border-red-200 bg-red-50/50',
                stage.status === 'active' && 'border-brand-200 bg-brand-50/30 ring-2 ring-brand-200',
                stage.status === 'pending' && 'border-gray-200 bg-gray-50 opacity-60',
              )}
            >
              {/* Stage header */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-lg font-bold text-gray-900">{target}%</span>
                {stage.status === 'passed' && <CheckCircle className="h-4 w-4 text-green-600" />}
                {stage.status === 'failed' && <XCircle className="h-4 w-4 text-red-600" />}
                {stage.status === 'active' && (
                  <span className="relative flex h-3 w-3">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-75" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-brand-500" />
                  </span>
                )}
                {stage.status === 'pending' && <Clock className="h-4 w-4 text-gray-400" />}
              </div>

              {/* Metrics */}
              {(stage.error_rate !== undefined || stage.latency_ms !== undefined) && (
                <div className="space-y-1">
                  {stage.error_rate !== undefined && (
                    <div className="flex items-center gap-1.5">
                      <AlertTriangle className={clsx('h-3 w-3', stage.error_rate > 1 ? 'text-red-500' : 'text-green-500')} />
                      <span className={clsx('text-[10px] font-medium', stage.error_rate > 1 ? 'text-red-600' : 'text-green-600')}>
                        {stage.error_rate.toFixed(2)}% error
                      </span>
                    </div>
                  )}
                  {stage.latency_ms !== undefined && (
                    <div className="flex items-center gap-1.5">
                      <Gauge className={clsx('h-3 w-3', stage.latency_ms > 500 ? 'text-yellow-500' : 'text-green-500')} />
                      <span className="text-[10px] text-gray-600">
                        {stage.latency_ms}ms p50
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Duration */}
              {stage.duration_seconds !== undefined && (
                <p className="mt-1 text-[10px] text-gray-400">
                  {formatDuration(stage.duration_seconds)}
                </p>
              )}
              {isActive && stage.started_at && (
                <p className="mt-1 text-[10px] text-brand-600 font-medium">
                  Live
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
