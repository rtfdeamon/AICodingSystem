import { useMemo } from 'react';
import {
  BarChart3,
  Clock,
  TrendingUp,
  CheckCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface ColumnStat {
  column: string;
  count: number;
  avg_time_hours: number;
}

interface PipelineStatsProps {
  columns: ColumnStat[];
  totalTickets: number;
  completedThisWeek: number;
  avgCycleTimeHours: number;
  throughputPerWeek: number[];
}

const COLUMN_CHART_COLORS = [
  'bg-gray-400',    // backlog
  'bg-blue-500',    // ai_planning
  'bg-purple-500',  // plan_review
  'bg-yellow-500',  // ai_coding
  'bg-pink-500',    // code_review
  'bg-green-500',   // staging
  'bg-red-500',     // staging_verification
  'bg-emerald-500', // production
];

function formatHours(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function formatColumnName(col: string): string {
  return col
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export function PipelineStats({
  columns,
  totalTickets,
  completedThisWeek,
  avgCycleTimeHours,
  throughputPerWeek,
}: PipelineStatsProps) {
  const maxColumnCount = useMemo(
    () => Math.max(...columns.map((c) => c.count), 1),
    [columns],
  );
  const maxThroughput = useMemo(
    () => Math.max(...throughputPerWeek, 1),
    [throughputPerWeek],
  );

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 className="h-4 w-4 text-blue-600" />
            <span className="text-xs text-gray-500">Total Tickets</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{totalTickets}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-xs text-gray-500">Completed This Week</span>
          </div>
          <p className="text-2xl font-bold text-green-600">{completedThisWeek}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="h-4 w-4 text-purple-600" />
            <span className="text-xs text-gray-500">Avg Cycle Time</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">{formatHours(avgCycleTimeHours)}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-4 w-4 text-orange-600" />
            <span className="text-xs text-gray-500">Avg Throughput</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">
            {throughputPerWeek.length > 0
              ? (throughputPerWeek.reduce((a, b) => a + b, 0) / throughputPerWeek.length).toFixed(1)
              : '--'}
            <span className="text-xs font-normal text-gray-400 ml-1">/wk</span>
          </p>
        </div>
      </div>

      {/* Tickets per column - vertical bars */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Tickets Per Column</h4>
        <div className="flex items-end gap-3 h-48">
          {columns.map((col, idx) => {
            const heightPct = (col.count / maxColumnCount) * 100;
            return (
              <div key={col.column} className="flex-1 flex flex-col items-center group relative">
                {/* Tooltip */}
                <div className="absolute -top-10 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <div className="rounded bg-gray-900 px-2 py-1 text-[10px] text-white whitespace-nowrap text-center">
                    <p>{col.count} tickets</p>
                    <p className="text-gray-400">avg {formatHours(col.avg_time_hours)}</p>
                  </div>
                </div>
                {/* Count label */}
                <span className="text-xs font-bold text-gray-700 mb-1">{col.count}</span>
                {/* Bar */}
                <div className="w-full flex-1 flex items-end">
                  <div
                    className={clsx(
                      'w-full rounded-t transition-all duration-500 hover:opacity-80 cursor-pointer min-h-[4px]',
                      COLUMN_CHART_COLORS[idx % COLUMN_CHART_COLORS.length],
                    )}
                    style={{ height: `${Math.max(heightPct, 2)}%` }}
                  />
                </div>
                {/* Label */}
                <span className="mt-2 text-[9px] text-gray-500 text-center leading-tight">
                  {formatColumnName(col.column)}
                </span>
              </div>
            );
          })}
        </div>

        {/* Average time per column */}
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 mb-2">Average Time Per Column</p>
          <div className="flex flex-wrap gap-2">
            {columns.map((col) => (
              <div key={col.column} className="flex items-center gap-1.5 rounded bg-gray-50 px-2 py-1">
                <span className="text-[10px] text-gray-500">{formatColumnName(col.column)}</span>
                <Badge variant="default">{formatHours(col.avg_time_hours)}</Badge>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Throughput per week - bar chart */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Weekly Throughput</h4>
        <div className="flex items-end gap-2 h-40">
          {throughputPerWeek.map((count, idx) => {
            const heightPct = (count / maxThroughput) * 100;
            return (
              <div key={idx} className="flex-1 flex flex-col items-center group relative">
                <div className="absolute -top-8 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <div className="rounded bg-gray-900 px-2 py-1 text-[10px] text-white">
                    {count} tickets
                  </div>
                </div>
                <div className="w-full flex-1 flex items-end">
                  <div
                    className="w-full rounded-t bg-brand-500 hover:bg-brand-600 transition-colors cursor-pointer min-h-[2px]"
                    style={{ height: `${Math.max(heightPct, 1)}%` }}
                  />
                </div>
                <span className="mt-1.5 text-[9px] text-gray-400">W{idx + 1}</span>
              </div>
            );
          })}
          {throughputPerWeek.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-400">No throughput data.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
