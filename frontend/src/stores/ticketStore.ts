import { create } from 'zustand';
import type {
  Ticket,
  Comment,
  AiPlan,
  AiCodeGeneration,
  AiLog,
  Review,
  TestResult,
  TicketHistory,
} from '@/types';
import { getTicket } from '@/api/tickets';
import { listComments } from '@/api/comments';
import { type Attachment, listAttachments } from '@/api/attachments';

interface TicketDetailState {
  currentTicket: Ticket | null;
  comments: Comment[];
  plans: AiPlan[];
  codeGens: AiCodeGeneration[];
  aiLogs: AiLog[];
  reviews: Review[];
  testResults: TestResult[];
  history: TicketHistory[];
  attachments: Attachment[];
  isLoading: boolean;
  error: string | null;

  fetchTicket: (id: string) => Promise<void>;
  fetchComments: (ticketId: string) => Promise<void>;
  fetchAttachments: (ticketId: string) => Promise<void>;
  setCurrentTicket: (ticket: Ticket | null) => void;
  addComment: (comment: Comment) => void;
  updateComment: (comment: Comment) => void;
  removeComment: (commentId: string) => void;
  addHistoryEntry: (entry: TicketHistory) => void;
  setPlan: (plan: AiPlan) => void;
  addCodeGen: (codeGen: AiCodeGeneration) => void;
  addAiLog: (log: AiLog) => void;
  addReview: (review: Review) => void;
  addTestResult: (result: TestResult) => void;
  addAttachment: (attachment: Attachment) => void;
  removeAttachment: (attachmentId: string) => void;
  reset: () => void;
}

const initialState = {
  currentTicket: null,
  comments: [],
  plans: [],
  codeGens: [],
  aiLogs: [],
  reviews: [],
  testResults: [],
  history: [],
  attachments: [],
  isLoading: false,
  error: null,
};

export const useTicketStore = create<TicketDetailState>((set) => ({
  ...initialState,

  fetchTicket: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const ticket = await getTicket(id);
      set({ currentTicket: ticket, isLoading: false });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || 'Failed to load ticket';
      set({ error: message, isLoading: false });
    }
  },

  fetchComments: async (ticketId) => {
    try {
      const comments = await listComments(ticketId);
      set({ comments });
    } catch {
      // silent failure for comments
    }
  },

  fetchAttachments: async (ticketId) => {
    try {
      const { items } = await listAttachments(ticketId);
      set({ attachments: items });
    } catch {
      // silent failure for attachments
    }
  },

  setCurrentTicket: (ticket) => set({ currentTicket: ticket }),

  addComment: (comment) =>
    set((state) => ({ comments: [...state.comments, comment] })),

  updateComment: (comment) =>
    set((state) => ({
      comments: state.comments.map((c) => (c.id === comment.id ? comment : c)),
    })),

  removeComment: (commentId) =>
    set((state) => ({
      comments: state.comments.filter((c) => c.id !== commentId),
    })),

  addHistoryEntry: (entry) =>
    set((state) => ({ history: [...state.history, entry] })),

  setPlan: (plan) =>
    set((state) => {
      const existing = state.plans.findIndex((p) => p.id === plan.id);
      if (existing >= 0) {
        const plans = [...state.plans];
        plans[existing] = plan;
        return { plans };
      }
      return { plans: [...state.plans, plan] };
    }),

  addCodeGen: (codeGen) =>
    set((state) => ({ codeGens: [...state.codeGens, codeGen] })),

  addAiLog: (log) =>
    set((state) => ({ aiLogs: [...state.aiLogs, log] })),

  addReview: (review) =>
    set((state) => ({ reviews: [...state.reviews, review] })),

  addTestResult: (result) =>
    set((state) => ({ testResults: [...state.testResults, result] })),

  addAttachment: (attachment) =>
    set((state) => ({ attachments: [...state.attachments, attachment] })),

  removeAttachment: (attachmentId) =>
    set((state) => ({
      attachments: state.attachments.filter((a) => a.id !== attachmentId),
    })),

  reset: () => set(initialState),
}));
