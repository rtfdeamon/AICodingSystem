import { useMemo } from 'react';
import {
  Shield,
  CheckCircle,
  TestTube,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import { clsx } from 'clsx';

export interface QualityTrend {
  date: string;
  lint_pass_rate: number;
  test_coverage_pct: number;
  vulnerability_count: number;
}

interface CodeQualityChartProps {
  lintPassRate: number;
  testCoveragePct: number;
  reviewPassRate: number;
  securityVulnerabilities: number;
  trends: QualityTrend[];
}

function TrendIndicator({ current, previous }: { current: number; previous: number }) {
  const diff = current - previous;
  if (Math.abs(diff) < 0.1) {
    return <Minus className="h-3 w-3 text-gray-400" />;
  }
  if (diff > 0) {
    return (
      <span className="flex items-center gap-0.5 text-[10px] text-green-600">
        <TrendingUp className="h-3 w-3" />
        +{diff.toFixed(1)}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-0.5 text-[10px] text-red-600">
      <TrendingDown className="h-3 w-3" />
      {diff.toFixed(1)}
    </span>
  );
}

export function CodeQualityChart({
  lintPassRate,
  testCoveragePct,
  reviewPassRate,
  securityVulnerabilities,
  trends,
}: CodeQualityChartProps) {
  const maxVulns = useMemo(
    () => Math.max(...trends.map((t) => t.vulnerability_count), 1),
    [trends],
  );

  // Previous values for trend comparison
  const prevTrend = trends.length >= 2 ? trends[trends.length - 2] : null;

  return (
    <div className="space-y-6">
      {/* Summary metric cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <span className="text-xs text-gray-500">Lint Pass Rate</span>
            </div>
            {prevTrend && (
              <TrendIndicator current={lintPassRate} previous={prevTrend.lint_pass_rate} />
            )}
          </div>
          <p className={clsx('text-2xl font-bold', lintPassRate >= 95 ? 'text-green-600' : lintPassRate >= 85 ? 'text-yellow-600' : 'text-red-600')}>
            {lintPassRate.toFixed(1)}%
          </p>
          <div className="mt-2 h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
            <div
              className={clsx('h-full rounded-full', lintPassRate >= 95 ? 'bg-green-500' : lintPassRate >= 85 ? 'bg-yellow-500' : 'bg-red-500')}
              style={{ width: `${lintPassRate}%` }}
            />
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TestTube className="h-4 w-4 text-blue-600" />
              <span className="text-xs text-gray-500">Test Coverage</span>
            </div>
            {prevTrend && (
              <TrendIndicator current={testCoveragePct} previous={prevTrend.test_coverage_pct} />
            )}
          </div>
          <p className={clsx('text-2xl font-bold', testCoveragePct >= 80 ? 'text-green-600' : testCoveragePct >= 60 ? 'text-yellow-600' : 'text-red-600')}>
            {testCoveragePct.toFixed(1)}%
          </p>
          <div className="mt-2 h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
            <div
              className={clsx('h-full rounded-full', testCoveragePct >= 80 ? 'bg-green-500' : testCoveragePct >= 60 ? 'bg-yellow-500' : 'bg-red-500')}
              style={{ width: `${testCoveragePct}%` }}
            />
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="h-4 w-4 text-purple-600" />
            <span className="text-xs text-gray-500">Review Pass Rate</span>
          </div>
          <p className={clsx('text-2xl font-bold', reviewPassRate >= 90 ? 'text-green-600' : 'text-yellow-600')}>
            {reviewPassRate.toFixed(1)}%
          </p>
          <div className="mt-2 h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
            <div
              className={clsx('h-full rounded-full', reviewPassRate >= 90 ? 'bg-green-500' : 'bg-yellow-500')}
              style={{ width: `${reviewPassRate}%` }}
            />
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className={clsx('h-4 w-4', securityVulnerabilities === 0 ? 'text-green-600' : 'text-red-600')} />
            <span className="text-xs text-gray-500">Vulnerabilities</span>
          </div>
          <p className={clsx('text-2xl font-bold', securityVulnerabilities === 0 ? 'text-green-600' : 'text-red-600')}>
            {securityVulnerabilities}
          </p>
        </div>
      </div>

      {/* Coverage trend over time */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Coverage Trend</h4>
        <div className="relative h-48">
          {/* Grid lines */}
          {[0, 25, 50, 75, 100].map((val) => (
            <div
              key={val}
              className="absolute w-full border-t border-gray-50 text-[9px] text-gray-300"
              style={{ bottom: `${val}%` }}
            >
              <span className="absolute -left-1 -translate-x-full">{val}%</span>
            </div>
          ))}

          {/* Line chart via SVG */}
          {trends.length > 1 && (
            <svg
              className="absolute inset-0 w-full h-full"
              preserveAspectRatio="none"
              viewBox={`0 0 ${trends.length - 1} 100`}
            >
              {/* Coverage line */}
              <polyline
                fill="none"
                stroke="#3b82f6"
                strokeWidth="0.8"
                points={trends
                  .map((t, i) => `${i},${100 - t.test_coverage_pct}`)
                  .join(' ')}
              />
              {/* Lint pass rate line */}
              <polyline
                fill="none"
                stroke="#22c55e"
                strokeWidth="0.8"
                strokeDasharray="1,0.5"
                points={trends
                  .map((t, i) => `${i},${100 - t.lint_pass_rate}`)
                  .join(' ')}
              />
            </svg>
          )}
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 bg-blue-500 rounded" />
            Test Coverage
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 bg-green-500 rounded border-dashed" style={{ borderBottom: '1px dashed #22c55e', height: 0 }} />
            Lint Pass Rate
          </span>
        </div>
      </div>

      {/* Security vulnerability count over time */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h4 className="text-sm font-semibold text-gray-900 mb-4">Vulnerability Count Over Time</h4>
        <div className="flex items-end gap-1 h-32">
          {trends.map((trend) => {
            const heightPct = (trend.vulnerability_count / maxVulns) * 100;
            const dateLabel = new Date(trend.date).toLocaleDateString('en', { month: 'short', day: 'numeric' });

            return (
              <div
                key={trend.date}
                className="flex-1 flex flex-col items-center group relative"
              >
                <div className="absolute -top-8 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <div className="rounded bg-gray-900 px-2 py-1 text-[10px] text-white whitespace-nowrap">
                    {trend.vulnerability_count} vulns
                  </div>
                </div>
                <div className="w-full flex-1 flex items-end">
                  <div
                    className={clsx(
                      'w-full rounded-t transition-colors cursor-pointer min-h-[2px]',
                      trend.vulnerability_count === 0 ? 'bg-green-400' : trend.vulnerability_count <= 3 ? 'bg-yellow-500' : 'bg-red-500',
                    )}
                    style={{ height: `${Math.max(heightPct, 2)}%` }}
                  />
                </div>
                <span className="mt-1 text-[9px] text-gray-400">{dateLabel}</span>
              </div>
            );
          })}
          {trends.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-400">No trend data.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
