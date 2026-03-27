import { create } from 'zustand';
import type { Ticket, ColumnName } from '@/types';
import * as kanbanApi from '@/api/kanban';
import { COLUMN_NAMES } from '@/utils/constants';

function emptyBoard(): Record<ColumnName, Ticket[]> {
  const board = {} as Record<ColumnName, Ticket[]>;
  COLUMN_NAMES.forEach((col) => {
    board[col] = [];
  });
  return board;
}

interface KanbanState {
  columns: Record<ColumnName, Ticket[]>;
  currentProjectId: string | null;
  isLoading: boolean;
  error: string | null;

  fetchBoard: (projectId: string) => Promise<void>;
  moveTicket: (ticketId: string, toColumn: ColumnName, position?: number) => Promise<void>;
  reorderTicket: (ticketId: string, newPosition: number) => Promise<void>;
  addTicket: (ticket: Ticket) => void;
  updateTicket: (ticket: Ticket) => void;
  removeTicket: (ticketId: string) => void;
}

export const useKanbanStore = create<KanbanState>((set, get) => ({
  columns: emptyBoard(),
  currentProjectId: null,
  isLoading: false,
  error: null,

  fetchBoard: async (projectId) => {
    set({ isLoading: true, error: null, currentProjectId: projectId });
    try {
      const board = await kanbanApi.getBoard(projectId);
      // Ensure all columns exist
      const columns = { ...emptyBoard(), ...board.columns };
      set({ columns, isLoading: false });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || 'Failed to load board';
      set({ error: message, isLoading: false });
    }
  },

  moveTicket: async (ticketId, toColumn, position) => {
    const prevColumns = { ...get().columns };

    // Optimistic update
    const cols = { ...get().columns };
    let ticket: Ticket | undefined;
    for (const col of COLUMN_NAMES) {
      const idx = cols[col].findIndex((t) => t.id === ticketId);
      if (idx !== -1) {
        ticket = { ...cols[col][idx], column_name: toColumn };
        cols[col] = cols[col].filter((_, i) => i !== idx);
        break;
      }
    }
    if (ticket) {
      const targetCol = [...cols[toColumn]];
      const pos = position ?? targetCol.length;
      targetCol.splice(pos, 0, ticket);
      cols[toColumn] = targetCol;
      set({ columns: cols });
    }

    try {
      await kanbanApi.moveTicket({ ticket_id: ticketId, to_column: toColumn });
    } catch {
      // Revert on failure
      set({ columns: prevColumns });
    }
  },

  reorderTicket: async (ticketId, newPosition) => {
    const prevColumns = { ...get().columns };

    // Optimistic reorder within same column
    const cols = { ...get().columns };
    for (const col of COLUMN_NAMES) {
      const idx = cols[col].findIndex((t) => t.id === ticketId);
      if (idx !== -1) {
        const [ticket] = cols[col].splice(idx, 1);
        cols[col].splice(newPosition, 0, ticket);
        set({ columns: cols });
        break;
      }
    }

    try {
      await kanbanApi.reorderTicket({ ticket_id: ticketId, position: newPosition });
    } catch {
      set({ columns: prevColumns });
    }
  },

  addTicket: (ticket) => {
    const cols = { ...get().columns };
    cols[ticket.column_name] = [...cols[ticket.column_name], ticket];
    set({ columns: cols });
  },

  updateTicket: (ticket) => {
    const cols = { ...get().columns };
    // Remove from all columns first
    for (const col of COLUMN_NAMES) {
      cols[col] = cols[col].filter((t) => t.id !== ticket.id);
    }
    // Add to correct column
    cols[ticket.column_name] = [...cols[ticket.column_name], ticket];
    set({ columns: cols });
  },

  removeTicket: (ticketId) => {
    const cols = { ...get().columns };
    for (const col of COLUMN_NAMES) {
      cols[col] = cols[col].filter((t) => t.id !== ticketId);
    }
    set({ columns: cols });
  },
}));
