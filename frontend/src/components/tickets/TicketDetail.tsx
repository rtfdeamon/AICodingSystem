import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  FileCode,
  TestTube,
  Bot,
  History,
  MessageSquare,
  Clipboard,
  Paperclip,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useTicketStore } from '@/stores/ticketStore';
import { Badge } from '@/components/common/Badge';
import { Avatar } from '@/components/common/Avatar';
import { Spinner } from '@/components/common/Spinner';
import { TicketComments } from './TicketComments';
import { TicketHistory } from './TicketHistory';
import { TicketAttachments } from './TicketAttachments';
import {
  formatColumnName,
  formatPriority,
  formatDate,
  formatRelativeTime,
} from '@/utils/formatters';
import { COLUMN_COLORS } from '@/utils/constants';

type Tab = 'comments' | 'plan' | 'code' | 'tests' | 'ai_logs' | 'history' | 'attachments';

const tabs: { id: Tab; label: string; icon: typeof MessageSquare }[] = [
  { id: 'comments', label: 'Comments', icon: MessageSquare },
  { id: 'attachments', label: 'Attachments', icon: Paperclip },
  { id: 'plan', label: 'Plan', icon: Clipboard },
  { id: 'code', label: 'Code', icon: FileCode },
  { id: 'tests', label: 'Tests', icon: TestTube },
  { id: 'ai_logs', label: 'AI Logs', icon: Bot },
  { id: 'history', label: 'History', icon: History },
];

const priorityVariant: Record<string, 'danger' | 'warning' | 'default' | 'success'> = {
  P0: 'danger',
  P1: 'warning',
  P2: 'default',
  P3: 'success',
};

const planStatusVariant: Record<string, 'success' | 'danger' | 'warning' | 'default'> = {
  approved: 'success',
  rejected: 'danger',
  pending: 'warning',
  superseded: 'default',
};

export function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const {
    currentTicket: ticket,
    plans,
    codeGens,
    aiLogs,
    testResults,
    history,
    attachments,
    isLoading,
    error,
    fetchTicket,
    fetchAttachments,
    reset,
  } = useTicketStore();

  const [activeTab, setActiveTab] = useState<Tab>('comments');

  useEffect(() => {
    if (id) {
      fetchTicket(id);
    }
    return () => reset();
  }, [id, fetchTicket, reset]);

  useEffect(() => {
    if (id && activeTab === 'attachments') {
      fetchAttachments(id);
    }
  }, [id, activeTab, fetchAttachments]);

  if (isLoading || !ticket) {
    return (
      <div className="flex h-full items-center justify-center">
        {isLoading ? (
          <Spinner size="lg" />
        ) : error ? (
          <div className="text-center">
            <p className="text-lg font-semibold text-red-600">Error</p>
            <p className="mt-1 text-sm text-gray-500">{error}</p>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl">
      {/* Back button */}
      <button
        onClick={() => navigate('/board')}
        className="mb-4 flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Board
      </button>

      {/* Main card */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        {/* Header */}
        <div className="border-b border-gray-200 p-6">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: COLUMN_COLORS[ticket.column_name] }}
                />
                <Badge variant="primary">{formatColumnName(ticket.column_name)}</Badge>
                <Badge variant={priorityVariant[ticket.priority] ?? 'default'} dot>
                  {formatPriority(ticket.priority)}
                </Badge>
                {ticket.story_points != null && (
                  <span className="text-xs text-gray-500 font-medium">
                    {ticket.story_points} pts
                  </span>
                )}
              </div>
              <h1 className="text-xl font-bold text-gray-900">{ticket.title}</h1>
            </div>
          </div>

          {/* Meta */}
          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-gray-500">
            {ticket.assignee && (
              <div className="flex items-center gap-2">
                <Avatar
                  name={ticket.assignee.full_name}
                  src={ticket.assignee.avatar_url}
                  size="sm"
                />
                <span>{ticket.assignee.full_name}</span>
              </div>
            )}
            <span>Created {formatDate(ticket.created_at)}</span>
            <span>Updated {formatRelativeTime(ticket.updated_at)}</span>
          </div>

          {/* Labels */}
          {ticket.labels && ticket.labels.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {ticket.labels.map((label) => (
                <span
                  key={label}
                  className="rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Description */}
        <div className="border-b border-gray-200 p-6">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Description</h3>
          <p className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">
            {ticket.description}
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200">
          <nav className="flex gap-0 px-6 overflow-x-auto scrollbar-thin">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap',
                  activeTab === tab.id
                    ? 'border-brand-600 text-brand-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700',
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
                {tab.id === 'attachments' && attachments.length > 0 && (
                  <span className="ml-1 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-gray-200 px-1.5 text-[10px] font-semibold text-gray-600">
                    {attachments.length}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab content */}
        <div className="p-6">
          {activeTab === 'comments' && <TicketComments ticketId={ticket.id} />}

          {activeTab === 'plan' && (
            <div>
              {plans.length === 0 ? (
                <div className="text-center py-12 text-sm text-gray-400">
                  No AI plan generated yet.
                </div>
              ) : (
                plans.map((plan) => (
                  <div key={plan.id} className="rounded-lg border border-gray-200 p-4 mb-4">
                    <div className="flex items-center justify-between mb-3">
                      <Badge variant={planStatusVariant[plan.status] ?? 'default'}>
                        {plan.status.charAt(0).toUpperCase() + plan.status.slice(1)}
                      </Badge>
                      <span className="text-xs text-gray-500">
                        v{plan.version} &middot; {plan.agent_name}
                      </span>
                    </div>
                    <div className="prose prose-sm max-w-none text-gray-700">
                      <pre className="whitespace-pre-wrap text-sm bg-gray-50 rounded-lg p-4">
                        {plan.plan_markdown}
                      </pre>
                    </div>
                    {plan.file_list.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-gray-500 mb-1">Files to change:</p>
                        <div className="flex flex-wrap gap-1">
                          {plan.file_list.map((f) => (
                            <code key={f} className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                              {f}
                            </code>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'code' && (
            <div>
              {codeGens.length === 0 ? (
                <div className="text-center py-12 text-sm text-gray-400">
                  No code generations yet.
                </div>
              ) : (
                codeGens.map((gen) => (
                  <div key={gen.id} className="rounded-lg border border-gray-200 p-4 mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">
                        Subtask #{gen.subtask_index} &middot; {gen.agent_name}
                      </span>
                      <Badge
                        variant={
                          gen.status === 'completed'
                            ? 'success'
                            : gen.status === 'failed'
                              ? 'danger'
                              : 'warning'
                        }
                      >
                        {gen.status}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>Branch: {gen.branch_name}</span>
                      {gen.commit_sha && <span>Commit: {gen.commit_sha.slice(0, 8)}</span>}
                      <span>Lint: {gen.lint_passed ? 'pass' : 'fail'}</span>
                      <span>Tests: {gen.test_passed ? 'pass' : 'fail'}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'tests' && (
            <div>
              {testResults.length === 0 ? (
                <div className="text-center py-12 text-sm text-gray-400">
                  No test results yet.
                </div>
              ) : (
                testResults.map((result) => (
                  <div key={result.id} className="rounded-lg border border-gray-200 p-4 mb-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-gray-700">
                        {result.run_type} &middot; {result.tool_name}
                      </span>
                      <Badge
                        variant={result.passed ? 'success' : 'danger'}
                      >
                        {result.passed ? 'Passed' : 'Failed'}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-4 gap-4 text-center">
                      <div>
                        <p className="text-2xl font-bold text-green-600">{result.passed_count}</p>
                        <p className="text-xs text-gray-500">Passed</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-red-600">{result.failed_count}</p>
                        <p className="text-xs text-gray-500">Failed</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-gray-400">{result.skipped_count}</p>
                        <p className="text-xs text-gray-500">Skipped</p>
                      </div>
                      {result.coverage_pct !== undefined && (
                        <div>
                          <p className="text-2xl font-bold text-blue-600">
                            {result.coverage_pct}%
                          </p>
                          <p className="text-xs text-gray-500">Coverage</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'ai_logs' && (
            <div>
              {aiLogs.length === 0 ? (
                <div className="text-center py-12 text-sm text-gray-400">
                  No AI logs yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {aiLogs.map((log) => (
                    <div
                      key={log.id}
                      className="rounded-lg border border-gray-200 p-3 flex items-start gap-3"
                    >
                      <div
                        className={clsx(
                          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                          log.status === 'success'
                            ? 'bg-green-50 text-green-600'
                            : log.status === 'timeout'
                              ? 'bg-yellow-50 text-yellow-600'
                              : log.status === 'fallback'
                                ? 'bg-blue-50 text-blue-600'
                                : 'bg-red-50 text-red-600',
                        )}
                      >
                        <Bot className="h-4 w-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900">
                            {log.agent_name}
                          </span>
                          <span className="text-xs text-gray-400">{log.action_type}</span>
                        </div>
                        {log.error_message && (
                          <p className="mt-1 text-xs text-red-600 truncate">
                            {log.error_message}
                          </p>
                        )}
                        <div className="mt-1 flex items-center gap-3 text-[10px] text-gray-400">
                          <span>{log.prompt_tokens + log.completion_tokens} tokens</span>
                          <span>{log.latency_ms}ms</span>
                          <span>${log.cost_usd.toFixed(4)}</span>
                          <span>{formatRelativeTime(log.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'attachments' && (
            <TicketAttachments ticketId={ticket.id} attachments={attachments} />
          )}

          {activeTab === 'history' && <TicketHistory history={history} />}
        </div>
      </div>
    </div>
  );
}
