import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  CheckSquare,
  Square,
  Bot,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

export interface Subtask {
  id: string;
  title: string;
  description: string;
  affected_files: string[];
  agent_hint: string;
  complexity: 'low' | 'medium' | 'high';
  dependencies: string[];
  completed: boolean;
}

interface PlanViewerProps {
  subtasks: Subtask[];
  onToggleSubtask?: (id: string) => void;
  readOnly?: boolean;
}

const complexityConfig = {
  low: { label: 'Low', variant: 'success' as const, color: 'text-green-600' },
  medium: { label: 'Medium', variant: 'warning' as const, color: 'text-yellow-600' },
  high: { label: 'High', variant: 'danger' as const, color: 'text-red-600' },
};

export function PlanViewer({ subtasks, onToggleSubtask, readOnly = false }: PlanViewerProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const completedCount = subtasks.filter((s) => s.completed).length;

  return (
    <div className="space-y-2">
      {/* Progress header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700">
            {completedCount} / {subtasks.length} subtasks
          </span>
        </div>
        <div className="h-2 w-48 rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-brand-600 transition-all duration-500"
            style={{ width: `${subtasks.length > 0 ? (completedCount / subtasks.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Subtask tree */}
      {subtasks.map((subtask, index) => {
        const isExpanded = expanded.has(subtask.id);
        const complexity = complexityConfig[subtask.complexity];
        const deps = subtask.dependencies
          .map((depId) => subtasks.find((s) => s.id === depId))
          .filter(Boolean);

        return (
          <div
            key={subtask.id}
            className={clsx(
              'rounded-lg border transition-colors',
              subtask.completed
                ? 'border-green-200 bg-green-50/50'
                : 'border-gray-200 bg-white',
            )}
          >
            {/* Subtask header */}
            <div className="flex items-center gap-3 p-3">
              {/* Checkbox */}
              <button
                onClick={() => onToggleSubtask?.(subtask.id)}
                disabled={readOnly}
                className={clsx(
                  'shrink-0 transition-colors',
                  readOnly ? 'cursor-default' : 'cursor-pointer hover:text-brand-600',
                  subtask.completed ? 'text-green-600' : 'text-gray-400',
                )}
              >
                {subtask.completed ? (
                  <CheckSquare className="h-5 w-5" />
                ) : (
                  <Square className="h-5 w-5" />
                )}
              </button>

              {/* Expand toggle */}
              <button
                onClick={() => toggleExpand(subtask.id)}
                className="shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </button>

              {/* Title + badges */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-gray-400 font-mono">#{index + 1}</span>
                  <span
                    className={clsx(
                      'text-sm font-medium',
                      subtask.completed ? 'text-gray-500 line-through' : 'text-gray-900',
                    )}
                  >
                    {subtask.title}
                  </span>
                  <Badge variant={complexity.variant}>{complexity.label}</Badge>
                  <Badge variant="purple">
                    <Bot className="h-3 w-3 mr-1" />
                    {subtask.agent_hint}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Expanded details */}
            {isExpanded && (
              <div className="border-t border-gray-100 px-12 py-3 space-y-3">
                {/* Description */}
                <p className="text-sm text-gray-600 leading-relaxed">{subtask.description}</p>

                {/* Affected files */}
                {subtask.affected_files.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1.5">Affected Files</p>
                    <div className="flex flex-wrap gap-1.5">
                      {subtask.affected_files.map((file) => (
                        <span
                          key={file}
                          className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-xs font-mono text-gray-700"
                        >
                          <FileCode className="h-3 w-3 text-gray-400" />
                          {file}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dependencies */}
                {deps.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1.5">Dependencies</p>
                    <div className="flex flex-wrap gap-2">
                      {deps.map((dep) => (
                        <span
                          key={dep!.id}
                          className="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
                        >
                          <ArrowRight className="h-3 w-3" />
                          {dep!.title}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {subtasks.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400">
          No subtasks in this plan.
        </div>
      )}
    </div>
  );
}
