import { create } from 'zustand';

/* ─── Types ─── */
export type TodoSeverity = 'critical' | 'warning' | 'info';
export type TodoStatus = 'open' | 'in_progress' | 'resolved' | 'verified';
export type TodoSource = 'auto:api' | 'auto:env' | 'auto:oauth' | 'auto:ws' | 'user';

export interface StatusChange {
  from: TodoStatus;
  to: TodoStatus;
  at: string;
  note?: string;
}

export interface TodoItem {
  id: string;
  timestamp: string;
  severity: TodoSeverity;
  status: TodoStatus;
  source: TodoSource;
  title: string;
  detail: string;
  /** Identifies the component / subsystem that reported the issue */
  identifier: string;
  resolvedAt?: string;
  verifiedAt?: string;
  /** Resolution feedback from user */
  resolution?: string;
  /** Status change history */
  history: StatusChange[];
  /** Check function identifier — used by verifyResolved */
  checkKey?: string;
}

interface TodoAssistantState {
  items: TodoItem[];
  isOpen: boolean;
  unreadCount: number;

  toggle: () => void;
  open: () => void;
  close: () => void;
  addTodo: (todo: Omit<TodoItem, 'id' | 'timestamp' | 'status' | 'history'> & { checkKey?: string }) => void;
  resolve: (id: string, resolution?: string) => void;
  verify: (id: string) => void;
  reopen: (id: string, reason?: string) => void;
  setInProgress: (id: string) => void;
  remove: (id: string) => void;
  clearResolved: () => void;
  markAllRead: () => void;
  /** Re-run env checks and auto-verify/reopen items based on results */
  verifyAll: () => Promise<void>;
}

const STORAGE_KEY = 'todo_assistant_items';

function loadItems(): TodoItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const items = raw ? JSON.parse(raw) : [];
    // Migrate old items without history
    return items.map((i: TodoItem) => ({ ...i, history: i.history || [] }));
  } catch {
    return [];
  }
}

function persistItems(items: TodoItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function makeId(): string {
  return `todo_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function isDuplicate(items: TodoItem[], title: string, identifier: string): boolean {
  return items.some(
    (i) => i.status !== 'verified' && i.title === title && i.identifier === identifier,
  );
}

function addStatusChange(item: TodoItem, to: TodoStatus, note?: string): StatusChange[] {
  return [
    ...item.history,
    { from: item.status, to, at: new Date().toISOString(), note },
  ];
}

export const useTodoAssistantStore = create<TodoAssistantState>((set, get) => ({
  items: loadItems(),
  isOpen: false,
  unreadCount: 0,

  toggle: () => set((s) => ({ isOpen: !s.isOpen, unreadCount: s.isOpen ? s.unreadCount : 0 })),
  open: () => set({ isOpen: true, unreadCount: 0 }),
  close: () => set({ isOpen: false }),

  addTodo: (todo) => {
    const { items } = get();
    if (isDuplicate(items, todo.title, todo.identifier)) return;

    const newItem: TodoItem = {
      ...todo,
      id: makeId(),
      timestamp: new Date().toISOString(),
      status: 'open',
      history: [{ from: 'open', to: 'open', at: new Date().toISOString(), note: 'Создано' }],
    };
    const next = [newItem, ...items];
    persistItems(next);
    set((s) => ({ items: next, unreadCount: s.unreadCount + 1 }));
  },

  resolve: (id, resolution) => {
    const next = get().items.map((i) =>
      i.id === id
        ? {
            ...i,
            status: 'resolved' as const,
            resolvedAt: new Date().toISOString(),
            resolution: resolution || i.resolution,
            history: addStatusChange(i, 'resolved', resolution || 'Отмечено как решённое'),
          }
        : i,
    );
    persistItems(next);
    set({ items: next });
  },

  verify: (id) => {
    const next = get().items.map((i) =>
      i.id === id
        ? {
            ...i,
            status: 'verified' as const,
            verifiedAt: new Date().toISOString(),
            history: addStatusChange(i, 'verified', 'Проверено — проблема подтверждённо решена'),
          }
        : i,
    );
    persistItems(next);
    set({ items: next });
  },

  setInProgress: (id) => {
    const next = get().items.map((i) =>
      i.id === id
        ? {
            ...i,
            status: 'in_progress' as const,
            history: addStatusChange(i, 'in_progress', 'Взято в работу'),
          }
        : i,
    );
    persistItems(next);
    set({ items: next });
  },

  reopen: (id, reason) => {
    const next = get().items.map((i) =>
      i.id === id
        ? {
            ...i,
            status: 'open' as const,
            resolvedAt: undefined,
            verifiedAt: undefined,
            resolution: undefined,
            history: addStatusChange(i, 'open', reason || 'Переоткрыто'),
          }
        : i,
    );
    persistItems(next);
    set((s) => ({ items: next, unreadCount: s.unreadCount + 1 }));
  },

  remove: (id) => {
    const next = get().items.filter((i) => i.id !== id);
    persistItems(next);
    set({ items: next });
  },

  clearResolved: () => {
    const next = get().items.filter((i) => i.status !== 'resolved' && i.status !== 'verified');
    persistItems(next);
    set({ items: next });
  },

  markAllRead: () => set({ unreadCount: 0 }),

  verifyAll: async () => {
    const { runVerificationChecks } = await import('@/utils/envDiagnostics');
    const results = await runVerificationChecks();
    const { items, resolve, reopen } = get();

    for (const item of items) {
      if (!item.checkKey) continue;
      const checkResult = results[item.checkKey];
      if (checkResult === undefined) continue;

      if (checkResult === true && item.status === 'open') {
        // Auto-resolve — the issue is fixed now
        resolve(item.id, 'Автоматически подтверждено: проблема устранена');
      } else if (checkResult === false && item.status === 'resolved') {
        // The issue is still there — reopen
        reopen(item.id, 'Автоверификация: проблема не решена, переоткрыто');
      }
    }
  },
}));
