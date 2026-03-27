import { useState } from 'react';
import {
  FileCode,
  FilePlus,
  FileX,
  FilePen,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';

interface AffectedFile {
  path: string;
  status: 'added' | 'modified' | 'deleted';
  estimated_additions: number;
  estimated_deletions: number;
  description?: string;
}

interface PlanDiffViewProps {
  files: AffectedFile[];
}

const fileStatusConfig = {
  added: { label: 'Added', icon: FilePlus, color: 'text-green-600', bg: 'bg-green-50', variant: 'success' as const },
  modified: { label: 'Modified', icon: FilePen, color: 'text-yellow-600', bg: 'bg-yellow-50', variant: 'warning' as const },
  deleted: { label: 'Deleted', icon: FileX, color: 'text-red-600', bg: 'bg-red-50', variant: 'danger' as const },
};

export function PlanDiffView({ files }: PlanDiffViewProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpand = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const totalAdditions = files.reduce((sum, f) => sum + f.estimated_additions, 0);
  const totalDeletions = files.reduce((sum, f) => sum + f.estimated_deletions, 0);

  const grouped = {
    added: files.filter((f) => f.status === 'added'),
    modified: files.filter((f) => f.status === 'modified'),
    deleted: files.filter((f) => f.status === 'deleted'),
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      {/* Summary header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <div className="flex items-center gap-2">
          <FileCode className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-semibold text-gray-900">
            {files.length} file{files.length !== 1 ? 's' : ''} affected
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs font-medium">
          <span className="text-green-600">+{totalAdditions}</span>
          <span className="text-red-600">-{totalDeletions}</span>
        </div>
      </div>

      {/* File list */}
      <div className="divide-y divide-gray-100">
        {files.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">
            No files affected.
          </div>
        ) : (
          files.map((file) => {
            const config = fileStatusConfig[file.status];
            const isExpanded = expanded.has(file.path);
            const StatusIcon = config.icon;

            return (
              <div key={file.path}>
                <button
                  onClick={() => toggleExpand(file.path)}
                  className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="shrink-0 text-gray-400">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </span>
                  <StatusIcon className={clsx('h-4 w-4 shrink-0', config.color)} />
                  <span className="flex-1 truncate font-mono text-sm text-gray-800">
                    {file.path}
                  </span>
                  <Badge variant={config.variant} className="shrink-0">
                    {config.label}
                  </Badge>
                  <div className="flex items-center gap-2 text-xs font-medium shrink-0">
                    {file.estimated_additions > 0 && (
                      <span className="text-green-600">+{file.estimated_additions}</span>
                    )}
                    {file.estimated_deletions > 0 && (
                      <span className="text-red-600">-{file.estimated_deletions}</span>
                    )}
                  </div>
                </button>

                {isExpanded && file.description && (
                  <div className="border-t border-gray-50 bg-gray-50 px-14 py-3">
                    <p className="text-sm text-gray-600">{file.description}</p>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Category summary footer */}
      {files.length > 0 && (
        <div className="flex items-center gap-4 border-t border-gray-200 px-5 py-3 text-xs text-gray-500">
          {grouped.added.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              {grouped.added.length} added
            </span>
          )}
          {grouped.modified.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-yellow-500" />
              {grouped.modified.length} modified
            </span>
          )}
          {grouped.deleted.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-red-500" />
              {grouped.deleted.length} deleted
            </span>
          )}
        </div>
      )}
    </div>
  );
}
