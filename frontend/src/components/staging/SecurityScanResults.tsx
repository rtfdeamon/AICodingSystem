import { useState } from 'react';
import {
  Shield,
  AlertCircle,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronRight,
  FileCode,
  Lightbulb,
  Filter,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface SecurityFinding {
  id: string;
  severity: Severity;
  rule: string;
  file: string;
  line: number;
  description: string;
  fix_suggestion?: string;
}

interface SecurityScanResultsProps {
  findings: SecurityFinding[];
  scanStatus: 'passed' | 'failed' | 'running';
  scannedAt?: string;
}

const severityConfig: Record<Severity, {
  icon: typeof AlertCircle;
  color: string;
  bg: string;
  label: string;
  variant: 'danger' | 'warning' | 'default' | 'primary' | 'success';
  order: number;
}> = {
  critical: { icon: AlertCircle, color: 'text-red-700', bg: 'bg-red-50', label: 'Critical', variant: 'danger', order: 0 },
  high: { icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50', label: 'High', variant: 'warning', order: 1 },
  medium: { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'Medium', variant: 'warning', order: 2 },
  low: { icon: Info, color: 'text-blue-600', bg: 'bg-blue-50', label: 'Low', variant: 'primary', order: 3 },
  info: { icon: Info, color: 'text-gray-500', bg: 'bg-gray-50', label: 'Info', variant: 'default', order: 4 },
};

export function SecurityScanResults({ findings, scanStatus, scannedAt }: SecurityScanResultsProps) {
  const [severityFilter, setSeverityFilter] = useState<Severity | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredFindings = (severityFilter
    ? findings.filter((f) => f.severity === severityFilter)
    : findings
  ).sort((a, b) => severityConfig[a.severity].order - severityConfig[b.severity].order);

  const bySeverity = Object.fromEntries(
    (['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map((sev) => [
      sev,
      findings.filter((f) => f.severity === sev).length,
    ]),
  ) as Record<Severity, number>;

  return (
    <div className="space-y-4">
      {/* Pass/fail header */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={clsx(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                scanStatus === 'passed' ? 'bg-green-100' : scanStatus === 'failed' ? 'bg-red-100' : 'bg-blue-100',
              )}
            >
              <Shield
                className={clsx(
                  'h-5 w-5',
                  scanStatus === 'passed' ? 'text-green-600' : scanStatus === 'failed' ? 'text-red-600' : 'text-blue-600',
                )}
              />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Security Scan</h3>
              {scannedAt && (
                <p className="text-[10px] text-gray-400">
                  Last scanned: {new Date(scannedAt).toLocaleString()}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {scanStatus === 'passed' ? (
              <Badge variant="success">
                <CheckCircle className="h-3 w-3 mr-1" />
                Passed
              </Badge>
            ) : scanStatus === 'failed' ? (
              <Badge variant="danger">
                <XCircle className="h-3 w-3 mr-1" />
                Failed
              </Badge>
            ) : (
              <Badge variant="primary">Running</Badge>
            )}
          </div>
        </div>

        {/* Severity counts */}
        <div className="mt-4 flex items-center gap-3">
          {(['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map((sev) => {
            const config = severityConfig[sev];
            const count = bySeverity[sev];
            return (
              <div
                key={sev}
                className={clsx(
                  'flex items-center gap-1.5 rounded-lg px-3 py-1.5',
                  config.bg,
                )}
              >
                <span className={clsx('text-lg font-bold', config.color)}>{count}</span>
                <span className={clsx('text-xs font-medium', config.color)}>{config.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-gray-400" />
        <button
          onClick={() => setSeverityFilter(null)}
          className={clsx(
            'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            !severityFilter ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
          )}
        >
          All ({findings.length})
        </button>
        {(['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map((sev) => {
          const count = bySeverity[sev];
          if (count === 0) return null;
          return (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={clsx(
                'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors capitalize',
                severityFilter === sev ? 'bg-brand-100 text-brand-700' : 'text-gray-500 hover:bg-gray-100',
              )}
            >
              {sev} ({count})
            </button>
          );
        })}
      </div>

      {/* Findings list */}
      <div className="space-y-2">
        {filteredFindings.map((finding) => {
          const config = severityConfig[finding.severity];
          const SevIcon = config.icon;
          const isExpanded = expanded.has(finding.id);

          return (
            <div
              key={finding.id}
              className={clsx('rounded-lg border overflow-hidden', {
                'border-red-200': finding.severity === 'critical',
                'border-orange-200': finding.severity === 'high',
                'border-yellow-200': finding.severity === 'medium',
                'border-blue-200': finding.severity === 'low',
                'border-gray-200': finding.severity === 'info',
              })}
            >
              <button
                onClick={() => toggleExpand(finding.id)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
              >
                <SevIcon className={clsx('h-4 w-4 shrink-0', config.color)} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{finding.description}</p>
                  <p className="text-[10px] text-gray-400 font-mono mt-0.5">
                    <FileCode className="h-3 w-3 inline mr-0.5" />
                    {finding.file}:{finding.line} &middot; {finding.rule}
                  </p>
                </div>
                <Badge variant={config.variant}>{config.label}</Badge>
                <span className="text-gray-400 shrink-0">
                  {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </span>
              </button>

              {isExpanded && (
                <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 space-y-2">
                  <p className="text-sm text-gray-600">{finding.description}</p>
                  {finding.fix_suggestion && (
                    <div className="flex items-start gap-2 rounded-lg bg-green-50 border border-green-200 px-3 py-2">
                      <Lightbulb className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-xs font-semibold text-green-800">Suggested Fix</p>
                        <p className="text-xs text-green-700 mt-0.5">{finding.fix_suggestion}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filteredFindings.length === 0 && (
          <div className="py-12 text-center">
            <Shield className="mx-auto h-8 w-8 text-green-400 mb-2" />
            <p className="text-sm text-gray-500">No security findings.</p>
          </div>
        )}
      </div>
    </div>
  );
}
