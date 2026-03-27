import { useState, useCallback } from 'react';
import {
  Columns,
  Rows,
  MessageSquarePlus,
  FileCode,
  Plus,
  Minus,
} from 'lucide-react';
import { clsx } from 'clsx';

export interface DiffLine {
  number_old?: number;
  number_new?: number;
  type: 'context' | 'add' | 'remove' | 'header';
  content: string;
}

export interface DiffFile {
  path: string;
  lines: DiffLine[];
  additions: number;
  deletions: number;
}

export interface InlineCommentData {
  file: string;
  line: number;
  body: string;
}

interface DiffViewerProps {
  files: DiffFile[];
  comments?: { file: string; line: number; id: string }[];
  onAddComment?: (file: string, line: number) => void;
}

type ViewMode = 'unified' | 'split';

export function DiffViewer({ files, comments = [], onAddComment }: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('unified');
  const [hoveredLine, setHoveredLine] = useState<string | null>(null);

  const getLineKey = useCallback((filePath: string, lineIdx: number) => {
    return `${filePath}:${lineIdx}`;
  }, []);

  const hasComment = useCallback(
    (filePath: string, line: number) => {
      return comments.some((c) => c.file === filePath && c.line === line);
    },
    [comments],
  );

  return (
    <div className="space-y-4">
      {/* View mode toggle */}
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={() => setViewMode('unified')}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            viewMode === 'unified'
              ? 'bg-brand-100 text-brand-700'
              : 'text-gray-500 hover:bg-gray-100',
          )}
        >
          <Rows className="h-3.5 w-3.5" />
          Unified
        </button>
        <button
          onClick={() => setViewMode('split')}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            viewMode === 'split'
              ? 'bg-brand-100 text-brand-700'
              : 'text-gray-500 hover:bg-gray-100',
          )}
        >
          <Columns className="h-3.5 w-3.5" />
          Side by Side
        </button>
      </div>

      {/* File diffs */}
      {files.map((file) => (
        <div key={file.path} className="rounded-lg border border-gray-200 overflow-hidden">
          {/* File header */}
          <div className="flex items-center justify-between bg-gray-50 px-4 py-2.5 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <FileCode className="h-4 w-4 text-gray-500" />
              <span className="font-mono text-sm font-medium text-gray-800">{file.path}</span>
            </div>
            <div className="flex items-center gap-3 text-xs font-medium">
              <span className="flex items-center gap-1 text-green-600">
                <Plus className="h-3 w-3" />{file.additions}
              </span>
              <span className="flex items-center gap-1 text-red-600">
                <Minus className="h-3 w-3" />{file.deletions}
              </span>
            </div>
          </div>

          {/* Diff content */}
          {viewMode === 'unified' ? (
            <UnifiedView
              file={file}
              hoveredLine={hoveredLine}
              setHoveredLine={setHoveredLine}
              getLineKey={getLineKey}
              hasComment={hasComment}
              onAddComment={onAddComment}
            />
          ) : (
            <SplitView
              file={file}
              hoveredLine={hoveredLine}
              setHoveredLine={setHoveredLine}
              getLineKey={getLineKey}
              hasComment={hasComment}
              onAddComment={onAddComment}
            />
          )}
        </div>
      ))}

      {files.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400">
          No diff content available.
        </div>
      )}
    </div>
  );
}

interface ViewProps {
  file: DiffFile;
  hoveredLine: string | null;
  setHoveredLine: (key: string | null) => void;
  getLineKey: (path: string, idx: number) => string;
  hasComment: (path: string, line: number) => boolean;
  onAddComment?: (file: string, line: number) => void;
}

function UnifiedView({ file, hoveredLine, setHoveredLine, getLineKey, hasComment, onAddComment }: ViewProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <tbody>
          {file.lines.map((line, idx) => {
            const lineKey = getLineKey(file.path, idx);
            const isHovered = hoveredLine === lineKey;
            const lineNum = line.number_new ?? line.number_old ?? 0;
            const showComment = hasComment(file.path, lineNum);

            return (
              <tr
                key={idx}
                onMouseEnter={() => setHoveredLine(lineKey)}
                onMouseLeave={() => setHoveredLine(null)}
                className={clsx(
                  'group',
                  line.type === 'add' && 'bg-green-50',
                  line.type === 'remove' && 'bg-red-50',
                  line.type === 'header' && 'bg-blue-50',
                )}
              >
                {/* Line numbers */}
                <td className="w-12 select-none border-r border-gray-100 px-2 py-0.5 text-right text-gray-400">
                  {line.number_old ?? ''}
                </td>
                <td className="w-12 select-none border-r border-gray-100 px-2 py-0.5 text-right text-gray-400">
                  {line.number_new ?? ''}
                </td>

                {/* Comment button */}
                <td className="w-8 text-center">
                  {(isHovered || showComment) && onAddComment && line.type !== 'header' && (
                    <button
                      onClick={() => onAddComment(file.path, lineNum)}
                      className={clsx(
                        'inline-flex items-center justify-center rounded p-0.5 transition-colors',
                        showComment
                          ? 'text-brand-600'
                          : 'text-gray-400 hover:text-brand-600',
                      )}
                    >
                      <MessageSquarePlus className="h-3.5 w-3.5" />
                    </button>
                  )}
                </td>

                {/* Content */}
                <td className="whitespace-pre px-3 py-0.5">
                  <span
                    className={clsx(
                      line.type === 'add' && 'text-green-800',
                      line.type === 'remove' && 'text-red-800',
                      line.type === 'header' && 'text-blue-700 font-semibold',
                      line.type === 'context' && 'text-gray-700',
                    )}
                  >
                    {line.type === 'add' && '+ '}
                    {line.type === 'remove' && '- '}
                    {line.type === 'context' && '  '}
                    {line.content}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SplitView({ file, hoveredLine, setHoveredLine, getLineKey, hasComment: _hasComment, onAddComment }: ViewProps) {
  // Build left (old) and right (new) columns
  const leftLines: (DiffLine | null)[] = [];
  const rightLines: (DiffLine | null)[] = [];

  let i = 0;
  while (i < file.lines.length) {
    const line = file.lines[i];
    if (line.type === 'header' || line.type === 'context') {
      leftLines.push(line);
      rightLines.push(line);
      i++;
    } else if (line.type === 'remove') {
      // Collect consecutive removes, then pair with adds
      const removes: DiffLine[] = [];
      while (i < file.lines.length && file.lines[i].type === 'remove') {
        removes.push(file.lines[i]);
        i++;
      }
      const adds: DiffLine[] = [];
      while (i < file.lines.length && file.lines[i].type === 'add') {
        adds.push(file.lines[i]);
        i++;
      }
      const maxLen = Math.max(removes.length, adds.length);
      for (let j = 0; j < maxLen; j++) {
        leftLines.push(j < removes.length ? removes[j] : null);
        rightLines.push(j < adds.length ? adds[j] : null);
      }
    } else if (line.type === 'add') {
      leftLines.push(null);
      rightLines.push(line);
      i++;
    } else {
      i++;
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <tbody>
          {leftLines.map((left, idx) => {
            const right = rightLines[idx];
            const lineKey = getLineKey(file.path, idx);
            const isHovered = hoveredLine === lineKey;

            return (
              <tr
                key={idx}
                onMouseEnter={() => setHoveredLine(lineKey)}
                onMouseLeave={() => setHoveredLine(null)}
                className="group"
              >
                {/* Left side */}
                <td
                  className={clsx(
                    'w-10 select-none border-r border-gray-100 px-2 py-0.5 text-right text-gray-400',
                    left?.type === 'remove' && 'bg-red-50',
                  )}
                >
                  {left?.number_old ?? ''}
                </td>
                <td
                  className={clsx(
                    'w-[50%] whitespace-pre px-3 py-0.5 border-r border-gray-200',
                    left?.type === 'remove' && 'bg-red-50 text-red-800',
                    left?.type === 'context' && 'text-gray-700',
                    left?.type === 'header' && 'bg-blue-50 text-blue-700',
                    !left && 'bg-gray-50',
                  )}
                >
                  {left?.content ?? ''}
                </td>

                {/* Right side */}
                <td
                  className={clsx(
                    'w-10 select-none border-r border-gray-100 px-2 py-0.5 text-right text-gray-400',
                    right?.type === 'add' && 'bg-green-50',
                  )}
                >
                  {right?.number_new ?? ''}
                </td>
                <td
                  className={clsx(
                    'w-[50%] whitespace-pre px-3 py-0.5',
                    right?.type === 'add' && 'bg-green-50 text-green-800',
                    right?.type === 'context' && 'text-gray-700',
                    right?.type === 'header' && 'bg-blue-50 text-blue-700',
                    !right && 'bg-gray-50',
                  )}
                >
                  {right?.content ?? ''}
                </td>

                {/* Add comment */}
                <td className="w-8 text-center">
                  {isHovered && onAddComment && (
                    <button
                      onClick={() => {
                        const lineNum = right?.number_new ?? left?.number_old ?? 0;
                        onAddComment(file.path, lineNum);
                      }}
                      className="text-gray-400 hover:text-brand-600 transition-colors"
                    >
                      <MessageSquarePlus className="h-3.5 w-3.5" />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
