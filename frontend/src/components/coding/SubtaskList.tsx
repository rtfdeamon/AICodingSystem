import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  CheckCircle,
  XCircle,
  Minus,
  ExternalLink,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface SubtaskFile {
  path: string;
  additions: number;
  deletions: number;
}

export interface SubtaskDetail {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'done' | 'failed';
  files_changed: SubtaskFile[];
  lint_passed: boolean | null;
  tests_passed: boolean | null;
  diff_url?: string;
}

interface SubtaskListProps {
  subtasks: SubtaskDetail[];
}

export function SubtaskList({ subtasks }: SubtaskListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {subtasks.map((subtask) => {
        const isExpanded = expanded.has(subtask.id);

        return (
          <div
            key={subtask.id}
            className="rounded-lg border border-gray-200 bg-white overflow-hidden"
          >
            {/* Header */}
            <button
              onClick={() => toggleExpand(subtask.id)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
            >
              <span className="shrink-0 text-gray-400">
                {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </span>

              <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                {subtask.title}
              </span>

              {/* Lint status */}
              <StatusBadge label="Lint" passed={subtask.lint_passed} />

              {/* Test status */}
              <StatusBadge label="Tests" passed={subtask.tests_passed} />

              {/* Files count */}
              <span className="text-xs text-gray-500 shrink-0">
                {subtask.files_changed.length} file{subtask.files_changed.length !== 1 ? 's' : ''}
              </span>

              {/* Status badge */}
              <Badge
                variant={
                  subtask.status === 'done' ? 'success'
                    : subtask.status === 'failed' ? 'danger'
                      : subtask.status === 'in_progress' ? 'warning'
                        : 'default'
                }
              >
                {subtask.status.replace('_', ' ')}
              </Badge>
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="border-t border-gray-100 px-4 py-3 space-y-3">
                <p className="text-sm text-gray-600">{subtask.description}</p>

                {/* Files changed table */}
                {subtask.files_changed.length > 0 && (
                  <div className="rounded-lg border border-gray-100 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">File</th>
                          <th className="px-3 py-2 text-right text-xs font-medium text-green-600 w-16">+</th>
                          <th className="px-3 py-2 text-right text-xs font-medium text-red-600 w-16">-</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {subtask.files_changed.map((file) => (
                          <tr key={file.path} className="hover:bg-gray-50">
                            <td className="px-3 py-2">
                              <span className="inline-flex items-center gap-1.5 font-mono text-xs text-gray-700">
                                <FileCode className="h-3.5 w-3.5 text-gray-400" />
                                {file.path}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-right text-xs font-medium text-green-600">
                              +{file.additions}
                            </td>
                            <td className="px-3 py-2 text-right text-xs font-medium text-red-600">
                              -{file.deletions}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Diff link */}
                {subtask.diff_url && (
                  <a
                    href={subtask.diff_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    View Full Diff
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })}

      {subtasks.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400">
          No subtasks available.
        </div>
      )}
    </div>
  );
}

function StatusBadge({ label, passed }: { label: string; passed: boolean | null }) {
  if (passed === null) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-gray-400 shrink-0">
        <Minus className="h-3 w-3" />
        {label}
      </span>
    );
  }
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 text-xs font-medium shrink-0',
        passed ? 'text-green-600' : 'text-red-600',
      )}
    >
      {passed ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {label}
    </span>
  );
}
