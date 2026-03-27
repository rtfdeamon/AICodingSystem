import { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  MinusCircle,
  ChevronDown,
  ChevronRight,
  TestTube,
  Shield,
  Layers,
  Monitor,
  Image,
  FileText,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface TestCase {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration_ms: number;
  error_message?: string;
  stack_trace?: string;
  screenshot_url?: string;
}

export interface TestSuite {
  id: string;
  name: string;
  type: 'unit' | 'integration' | 'e2e' | 'security';
  passed: number;
  failed: number;
  skipped: number;
  coverage_pct?: number;
  test_cases: TestCase[];
}

interface TestResultsPanelProps {
  suites: TestSuite[];
}

const typeIcons = {
  unit: TestTube,
  integration: Layers,
  e2e: Monitor,
  security: Shield,
};

const typeColors = {
  unit: 'text-blue-600 bg-blue-50',
  integration: 'text-purple-600 bg-purple-50',
  e2e: 'text-orange-600 bg-orange-50',
  security: 'text-red-600 bg-red-50',
};

export function TestResultsPanel({ suites }: TestResultsPanelProps) {
  const [expandedSuites, setExpandedSuites] = useState<Set<string>>(new Set());
  const [expandedCases, setExpandedCases] = useState<Set<string>>(new Set());
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const toggleSuite = (id: string) => {
    setExpandedSuites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleCase = (key: string) => {
    setExpandedCases((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Calculate totals
  const totalPassed = suites.reduce((s, suite) => s + suite.passed, 0);
  const totalFailed = suites.reduce((s, suite) => s + suite.failed, 0);
  const totalSkipped = suites.reduce((s, suite) => s + suite.skipped, 0);
  const totalTests = totalPassed + totalFailed + totalSkipped;
  const avgCoverage = suites.filter((s) => s.coverage_pct !== undefined).length > 0
    ? suites.reduce((s, suite) => s + (suite.coverage_pct ?? 0), 0) /
      suites.filter((s) => s.coverage_pct !== undefined).length
    : null;

  const filteredSuites = typeFilter
    ? suites.filter((s) => s.type === typeFilter)
    : suites;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{totalTests}</p>
            <p className="text-xs text-gray-500">Total Tests</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-green-600">{totalPassed}</p>
            <p className="text-xs text-gray-500">Passed</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-red-600">{totalFailed}</p>
            <p className="text-xs text-gray-500">Failed</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-400">{totalSkipped}</p>
            <p className="text-xs text-gray-500">Skipped</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-600">
              {avgCoverage !== null ? `${avgCoverage.toFixed(1)}%` : '--'}
            </p>
            <p className="text-xs text-gray-500">Coverage</p>
          </div>
        </div>

        {/* Pass rate progress */}
        <div className="mt-4">
          <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden flex">
            {totalTests > 0 && (
              <>
                <div
                  className="h-full bg-green-500 transition-all"
                  style={{ width: `${(totalPassed / totalTests) * 100}%` }}
                />
                <div
                  className="h-full bg-red-500 transition-all"
                  style={{ width: `${(totalFailed / totalTests) * 100}%` }}
                />
                <div
                  className="h-full bg-gray-300 transition-all"
                  style={{ width: `${(totalSkipped / totalTests) * 100}%` }}
                />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Type filter */}
      <div className="flex gap-2">
        <button
          onClick={() => setTypeFilter(null)}
          className={clsx(
            'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            !typeFilter ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
          )}
        >
          All
        </button>
        {(['unit', 'integration', 'e2e', 'security'] as const).map((type) => {
          const TypeIcon = typeIcons[type];
          return (
            <button
              key={type}
              onClick={() => setTypeFilter(type)}
              className={clsx(
                'inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors capitalize',
                typeFilter === type ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
              )}
            >
              <TypeIcon className="h-3 w-3" />
              {type}
            </button>
          );
        })}
      </div>

      {/* Suites */}
      <div className="space-y-2">
        {filteredSuites.map((suite) => {
          const isExpanded = expandedSuites.has(suite.id);
          const TypeIcon = typeIcons[suite.type];
          const allPassed = suite.failed === 0;

          return (
            <div
              key={suite.id}
              className={clsx(
                'rounded-lg border overflow-hidden transition-colors',
                allPassed ? 'border-green-200' : 'border-red-200',
              )}
            >
              {/* Suite header */}
              <button
                onClick={() => toggleSuite(suite.id)}
                className={clsx(
                  'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
                  allPassed ? 'bg-green-50/50 hover:bg-green-50' : 'bg-red-50/50 hover:bg-red-50',
                )}
              >
                <span className="text-gray-400 shrink-0">
                  {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </span>
                <div className={clsx('flex h-7 w-7 items-center justify-center rounded-md shrink-0', typeColors[suite.type])}>
                  <TypeIcon className="h-3.5 w-3.5" />
                </div>
                <span className="flex-1 text-sm font-medium text-gray-900">{suite.name}</span>
                <span className="text-xs text-green-600 font-medium">{suite.passed} passed</span>
                {suite.failed > 0 && (
                  <span className="text-xs text-red-600 font-medium">{suite.failed} failed</span>
                )}
                {suite.skipped > 0 && (
                  <span className="text-xs text-gray-400">{suite.skipped} skipped</span>
                )}
                {suite.coverage_pct !== undefined && (
                  <Badge variant={suite.coverage_pct >= 80 ? 'success' : suite.coverage_pct >= 60 ? 'warning' : 'danger'}>
                    {suite.coverage_pct}%
                  </Badge>
                )}
              </button>

              {/* Test cases */}
              {isExpanded && (
                <div className="border-t border-gray-100 divide-y divide-gray-50">
                  {suite.test_cases.map((tc, idx) => {
                    const caseKey = `${suite.id}-${idx}`;
                    const isCaseExpanded = expandedCases.has(caseKey);
                    const hasDetails = tc.error_message || tc.stack_trace || tc.screenshot_url;

                    return (
                      <div key={caseKey}>
                        <button
                          onClick={() => hasDetails && toggleCase(caseKey)}
                          className={clsx(
                            'flex w-full items-center gap-3 px-4 py-2 text-left transition-colors',
                            hasDetails && 'hover:bg-gray-50 cursor-pointer',
                            !hasDetails && 'cursor-default',
                          )}
                        >
                          {tc.status === 'passed' && <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />}
                          {tc.status === 'failed' && <XCircle className="h-4 w-4 text-red-500 shrink-0" />}
                          {tc.status === 'skipped' && <MinusCircle className="h-4 w-4 text-gray-400 shrink-0" />}
                          <span className="flex-1 text-xs text-gray-700 truncate">{tc.name}</span>
                          <span className="text-[10px] text-gray-400 shrink-0">{tc.duration_ms}ms</span>
                          {hasDetails && (
                            <span className="text-gray-400 shrink-0">
                              {isCaseExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            </span>
                          )}
                        </button>

                        {isCaseExpanded && hasDetails && (
                          <div className="bg-gray-50 px-12 py-3 space-y-2">
                            {tc.error_message && (
                              <div>
                                <p className="text-[10px] font-semibold text-red-600 mb-1">Error</p>
                                <p className="text-xs text-red-700 bg-red-50 rounded p-2 font-mono">
                                  {tc.error_message}
                                </p>
                              </div>
                            )}
                            {tc.stack_trace && (
                              <div>
                                <p className="text-[10px] font-semibold text-gray-500 mb-1">
                                  <FileText className="h-3 w-3 inline mr-1" />
                                  Stack Trace
                                </p>
                                <pre className="text-[10px] text-gray-600 bg-gray-900 text-gray-300 rounded p-2 overflow-x-auto max-h-40">
                                  {tc.stack_trace}
                                </pre>
                              </div>
                            )}
                            {tc.screenshot_url && (
                              <div>
                                <p className="text-[10px] font-semibold text-gray-500 mb-1">
                                  <Image className="h-3 w-3 inline mr-1" />
                                  Screenshot
                                </p>
                                <img
                                  src={tc.screenshot_url}
                                  alt="E2E failure screenshot"
                                  className="rounded-lg border border-gray-200 max-w-md"
                                />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {filteredSuites.length === 0 && (
          <div className="py-12 text-center text-sm text-gray-400">
            No test results available.
          </div>
        )}
      </div>
    </div>
  );
}
