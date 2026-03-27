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
import { getPlans } from '@/api/plans';
import * as aiLogsApi from '@/api/aiLogs';
import * as testResultsApi from '@/api/testResults';
import { getReviews } from '@/api/reviews';
import { listHistory } from '@/api/ticketHistory';

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
  fetchPlans: (ticketId: string) => Promise<void>;
  fetchAiLogs: (ticketId: string) => Promise<void>;
  fetchTestResults: (ticketId: string) => Promise<void>;
  fetchReviews: (ticketId: string) => Promise<void>;
  fetchHistory: (ticketId: string) => Promise<void>;
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

  fetchPlans: async (ticketId) => {
    try {
      const plans = await getPlans(ticketId);
      set({ plans });
    } catch {
      // silent failure — plans may not exist yet
    }
  },

  fetchAiLogs: async (ticketId) => {
    try {
      const res = await aiLogsApi.list({ ticket_id: ticketId });
      const logs: AiLog[] = res.items.map((entry) => ({
        id: entry.id,
        ticket_id: entry.ticket_id,
        agent_name: entry.agent,
        action_type: entry.action,
        model_id: entry.model,
        prompt_tokens: entry.input_tokens,
        completion_tokens: entry.output_tokens,
        cost_usd: entry.cost_usd,
        latency_ms: entry.duration_ms,
        status: entry.status as AiLog['status'],
        error_message: entry.error_message,
        created_at: entry.created_at,
      }));
      set({ aiLogs: logs });
    } catch {
      // silent failure
    }
  },

  fetchTestResults: async (ticketId) => {
    try {
      const results = await testResultsApi.list(ticketId);
      set({ testResults: results });
    } catch {
      // silent failure
    }
  },

  fetchReviews: async (ticketId) => {
    try {
      const reviews = await getReviews(ticketId);
      set({ reviews });
    } catch {
      // silent failure
    }
  },

  fetchHistory: async (ticketId) => {
    try {
      const history = await listHistory(ticketId);
      set({ history });
    } catch {
      // silent failure
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
