import { useState, useEffect, useRef, FormEvent } from 'react';
import {
  ClipboardCheck,
  X,
  Plus,
  Trash2,
  CheckCircle2,
  RotateCcw,
  AlertTriangle,
  AlertCircle,
  Info,
  Sparkles,
  RefreshCw,
  Play,
  ShieldCheck,
  Clock,
  ChevronDown,
  ChevronUp,
  Send,
  History,
} from 'lucide-react';
import {
  useTodoAssistantStore,
  type TodoItem,
  type TodoSeverity,
  type TodoStatus,
} from '@/stores/todoAssistantStore';
import { runEnvDiagnostics } from '@/utils/envDiagnostics';

/* ─── Severity config ─── */
const severityConfig: Record<
  TodoSeverity,
  { icon: typeof AlertCircle; color: string; bg: string; badge: string }
> = {
  critical: {
    icon: AlertCircle,
    color: 'text-red-600',
    bg: 'bg-red-50 border-red-200',
    badge: 'bg-red-100 text-red-700',
  },
  warning: {
    icon: AlertTriangle,
    color: 'text-amber-600',
    bg: 'bg-amber-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
  },
  info: {
    icon: Info,
    color: 'text-blue-600',
    bg: 'bg-blue-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
  },
};

const statusConfig: Record<TodoStatus, { label: string; color: string; icon: typeof Clock }> = {
  open: { label: 'Открыта', color: 'text-red-600', icon: AlertCircle },
  in_progress: { label: 'В работе', color: 'text-blue-600', icon: Play },
  resolved: { label: 'Решена', color: 'text-green-600', icon: CheckCircle2 },
  verified: { label: 'Подтверждена', color: 'text-emerald-700', icon: ShieldCheck },
};

const sourceLabels: Record<string, string> = {
  'auto:api': 'API Monitor',
  'auto:env': 'Env Check',
  'auto:oauth': 'OAuth Check',
  'auto:ws': 'WebSocket',
  user: 'Вручную',
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/* ─── Resolution Form (inline) ─── */
function ResolutionForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (text: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState('');
  return (
    <div className="mt-2 flex items-center gap-1">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Как решено? (Enter)"
        className="flex-1 rounded border border-gray-300 px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-brand-500"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            onSubmit(text || 'Решено');
          }
          if (e.key === 'Escape') onCancel();
        }}
      />
      <button
        onClick={() => onSubmit(text || 'Решено')}
        className="rounded p-1 text-green-600 hover:bg-green-100 transition-colors"
        title="Отправить"
      >
        <Send className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={onCancel}
        className="rounded p-1 text-gray-400 hover:bg-gray-200 transition-colors"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/* ─── Status History ─── */
function StatusHistory({ item }: { item: TodoItem }) {
  if (!item.history || item.history.length <= 1) return null;

  return (
    <div className="mt-2 border-t border-gray-200 pt-2">
      <p className="text-[10px] font-medium text-gray-500 mb-1 flex items-center gap-1">
        <History className="h-3 w-3" /> История
      </p>
      <div className="space-y-0.5">
        {item.history
          .slice()
          .reverse()
          .map((h, idx) => (
            <div key={idx} className="flex items-center gap-1.5 text-[10px]">
              <span className="text-gray-400 w-[100px] shrink-0">{formatTime(h.at)}</span>
              <span className={`font-medium ${statusConfig[h.to]?.color || 'text-gray-600'}`}>
                {statusConfig[h.to]?.label || h.to}
              </span>
              {h.note && <span className="text-gray-400 truncate">— {h.note}</span>}
            </div>
          ))}
      </div>
    </div>
  );
}

/* ─── Todo Card ─── */
function TodoCard({ item }: { item: TodoItem }) {
  const { resolve, verify, reopen, setInProgress, remove } = useTodoAssistantStore();
  const [showResolveForm, setShowResolveForm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const cfg = severityConfig[item.severity];
  const Icon = cfg.icon;
  const stCfg = statusConfig[item.status];
  const StIcon = stCfg.icon;
  const isResolved = item.status === 'resolved';
  const isVerified = item.status === 'verified';
  const isDone = isResolved || isVerified;

  return (
    <div
      className={`relative rounded-lg border p-3 transition-all ${
        isVerified
          ? 'bg-emerald-50/50 border-emerald-200 opacity-50'
          : isResolved
            ? 'bg-gray-50 border-gray-200 opacity-70'
            : item.status === 'in_progress'
              ? 'bg-blue-50 border-blue-200'
              : cfg.bg
      }`}
    >
      {/* Header */}
      <div className="flex items-start gap-2">
        <Icon
          className={`mt-0.5 h-4 w-4 shrink-0 ${isDone ? 'text-gray-400' : cfg.color}`}
        />
        <div className="flex-1 min-w-0">
          <p
            className={`text-sm font-medium leading-tight ${
              isDone ? 'text-gray-500 line-through' : 'text-gray-900'
            }`}
          >
            {item.title}
          </p>
          <p className="mt-1 text-xs text-gray-500 leading-relaxed">{item.detail}</p>
          {item.resolution && (
            <p className="mt-1 text-xs text-green-700 bg-green-50 rounded px-2 py-0.5 inline-block">
              {item.resolution}
            </p>
          )}
        </div>
      </div>

      {/* Meta row */}
      <div className="mt-2 flex items-center gap-1.5 flex-wrap">
        <span
          className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.badge}`}
        >
          {item.severity}
        </span>
        <span
          className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${
            isDone
              ? 'bg-green-100 text-green-700'
              : item.status === 'in_progress'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-600'
          }`}
        >
          <StIcon className="h-2.5 w-2.5" />
          {stCfg.label}
        </span>
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">
          {sourceLabels[item.source] || item.source}
        </span>
        <span className="text-[10px] text-gray-400 ml-auto">{formatTime(item.timestamp)}</span>
      </div>

      {/* ID row */}
      <div className="mt-1 flex items-center gap-2">
        <span className="text-[10px] text-gray-400 font-mono">{item.identifier}</span>
        {item.history && item.history.length > 1 && (
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-[10px] text-gray-400 hover:text-gray-600 flex items-center gap-0.5 transition-colors"
          >
            <History className="h-3 w-3" />
            {showHistory ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
          </button>
        )}
      </div>

      {/* History (collapsible) */}
      {showHistory && <StatusHistory item={item} />}

      {/* Resolution form */}
      {showResolveForm && (
        <ResolutionForm
          onSubmit={(text) => {
            resolve(item.id, text);
            setShowResolveForm(false);
          }}
          onCancel={() => setShowResolveForm(false)}
        />
      )}

      {/* Actions */}
      <div className="mt-2 flex items-center gap-1 flex-wrap">
        {isVerified ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-medium">
            <ShieldCheck className="h-3 w-3" /> Подтверждено
          </span>
        ) : isResolved ? (
          <>
            <button
              onClick={() => verify(item.id)}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-100 transition-colors"
              title="Подтвердить, что проблема действительно решена"
            >
              <ShieldCheck className="h-3 w-3" /> Подтвердить
            </button>
            <button
              onClick={() => reopen(item.id, 'Не решено — переоткрыто вручную')}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-amber-600 hover:bg-amber-100 transition-colors"
            >
              <RotateCcw className="h-3 w-3" /> Не решено
            </button>
          </>
        ) : item.status === 'in_progress' ? (
          <button
            onClick={() => setShowResolveForm(true)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-green-700 hover:bg-green-100 transition-colors"
          >
            <CheckCircle2 className="h-3 w-3" /> Решено
          </button>
        ) : (
          <>
            <button
              onClick={() => setInProgress(item.id)}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-blue-600 hover:bg-blue-100 transition-colors"
            >
              <Play className="h-3 w-3" /> В работу
            </button>
            <button
              onClick={() => setShowResolveForm(true)}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-green-700 hover:bg-green-100 transition-colors"
            >
              <CheckCircle2 className="h-3 w-3" /> Решено
            </button>
          </>
        )}
        <button
          onClick={() => remove(item.id)}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-red-500 hover:bg-red-100 transition-colors ml-auto"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

/* ─── Add Todo Form ─── */
function AddTodoForm({ onDone }: { onDone: () => void }) {
  const { addTodo } = useTodoAssistantStore();
  const [title, setTitle] = useState('');
  const [detail, setDetail] = useState('');
  const [severity, setSeverity] = useState<TodoSeverity>('warning');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    addTodo({
      severity,
      source: 'user',
      title: title.trim(),
      detail: detail.trim() || 'Добавлено пользователем',
      identifier: `user:manual:${Date.now()}`,
    });
    setTitle('');
    setDetail('');
    onDone();
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-gray-200 p-3 space-y-2 bg-gray-50">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Что нужно исправить..."
        className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        autoFocus
      />
      <textarea
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
        placeholder="Детали (необязательно)"
        rows={2}
        className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
      />
      <div className="flex items-center gap-2">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as TodoSeverity)}
          className="rounded-md border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onDone}
          className="rounded-md px-3 py-1 text-xs text-gray-500 hover:bg-gray-200 transition-colors"
        >
          Отмена
        </button>
        <button
          type="submit"
          className="rounded-md bg-brand-600 px-3 py-1 text-xs text-white hover:bg-brand-700 transition-colors"
        >
          Добавить
        </button>
      </div>
    </form>
  );
}

/* ─── Main Component ─── */
export function FloatingAssistant() {
  const { items, isOpen, unreadCount, toggle, close, clearResolved, verifyAll } =
    useTodoAssistantStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [filter, setFilter] = useState<'all' | 'open' | 'in_progress' | 'resolved'>('all');
  const [isScanning, setIsScanning] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Run diagnostics on mount
  useEffect(() => {
    // Clear old localStorage items from previous session for auto-detected issues
    // They'll be re-detected fresh
    const stored = localStorage.getItem('todo_assistant_items');
    if (stored) {
      try {
        const items = JSON.parse(stored) as TodoItem[];
        const manual = items.filter((i) => i.source === 'user');
        localStorage.setItem('todo_assistant_items', JSON.stringify(manual));
      } catch {
        // ignore
      }
    }

    const timer = setTimeout(() => {
      runEnvDiagnostics();
    }, 1500);
    return () => clearTimeout(timer);
  }, []);

  const filtered = items.filter((i) => {
    if (filter === 'open') return i.status === 'open';
    if (filter === 'in_progress') return i.status === 'in_progress';
    if (filter === 'resolved') return i.status === 'resolved' || i.status === 'verified';
    return true;
  });

  const openCount = items.filter((i) => i.status === 'open').length;
  const inProgressCount = items.filter((i) => i.status === 'in_progress').length;
  const criticalCount = items.filter(
    (i) => i.status === 'open' && i.severity === 'critical',
  ).length;

  const handleRescan = async () => {
    setIsScanning(true);
    await runEnvDiagnostics();
    setIsScanning(false);
  };

  const handleVerifyAll = async () => {
    setIsVerifying(true);
    await verifyAll();
    setIsVerifying(false);
  };

  return (
    <>
      {/* ─── Floating Button ─── */}
      <button
        onClick={toggle}
        className={`fixed bottom-6 right-6 z-[9999] flex items-center justify-center rounded-full shadow-lg transition-all duration-300 hover:scale-110 ${
          criticalCount > 0
            ? 'bg-red-600 hover:bg-red-700 h-14 w-14 animate-pulse'
            : openCount > 0
              ? 'bg-amber-500 hover:bg-amber-600 h-14 w-14'
              : inProgressCount > 0
                ? 'bg-blue-500 hover:bg-blue-600 h-13 w-13'
                : 'bg-green-600 hover:bg-green-700 h-12 w-12'
        }`}
        title="TODO Ассистент — Диагностика системы"
      >
        <ClipboardCheck className="h-6 w-6 text-white" />
        {(unreadCount > 0 || openCount > 0) && (
          <span className="absolute -top-1 -right-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-white text-[10px] font-bold text-red-600 shadow px-1">
            {unreadCount > 0 ? unreadCount : openCount}
          </span>
        )}
      </button>

      {/* ─── Panel ─── */}
      {isOpen && (
        <div
          ref={panelRef}
          className="fixed bottom-24 right-6 z-[9999] w-[420px] max-h-[calc(100vh-140px)] flex flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl animate-fade-in"
        >
          {/* Header */}
          <div className="flex items-center gap-3 border-b border-gray-200 px-4 py-3">
            <Sparkles className="h-5 w-5 text-brand-600" />
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-gray-900">TODO Ассистент</h3>
              <p className="text-[11px] text-gray-500">
                {openCount} откр. · {inProgressCount} в работе · {items.length} всего
              </p>
            </div>
            <button
              onClick={handleVerifyAll}
              disabled={isVerifying}
              className="rounded-lg p-1.5 text-emerald-500 hover:bg-emerald-50 hover:text-emerald-700 transition-colors"
              title="Проверить решённые задачи"
            >
              <ShieldCheck className={`h-4 w-4 ${isVerifying ? 'animate-pulse' : ''}`} />
            </button>
            <button
              onClick={handleRescan}
              disabled={isScanning}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
              title="Перепроверить окружение"
            >
              <RefreshCw className={`h-4 w-4 ${isScanning ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={close}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-1 border-b border-gray-100 px-4 py-2">
            {(
              [
                ['all', 'Все'],
                ['open', 'Открытые'],
                ['in_progress', 'В работе'],
                ['resolved', 'Решённые'],
              ] as const
            ).map(([f, label]) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  filter === f
                    ? 'bg-brand-100 text-brand-700'
                    : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                {label}
              </button>
            ))}
            <div className="flex-1" />
            {items.some((i) => i.status === 'resolved' || i.status === 'verified') && (
              <button
                onClick={clearResolved}
                className="text-[10px] text-gray-400 hover:text-red-500 transition-colors"
              >
                Очистить
              </button>
            )}
          </div>

          {/* Item list */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                <CheckCircle2 className="h-10 w-10 mb-2 text-green-400" />
                <p className="text-sm font-medium">
                  {filter === 'all' ? 'Всё чисто!' : 'Нет задач в этом фильтре'}
                </p>
                <p className="text-xs">
                  {filter === 'all'
                    ? 'Проблем не обнаружено'
                    : 'Попробуйте другой фильтр'}
                </p>
              </div>
            ) : (
              filtered.map((item) => <TodoCard key={item.id} item={item} />)
            )}
          </div>

          {/* Add form / button */}
          {showAddForm ? (
            <AddTodoForm onDone={() => setShowAddForm(false)} />
          ) : (
            <div className="border-t border-gray-200 p-2">
              <button
                onClick={() => setShowAddForm(true)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700 transition-colors"
              >
                <Plus className="h-4 w-4" />
                Добавить задачу
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
