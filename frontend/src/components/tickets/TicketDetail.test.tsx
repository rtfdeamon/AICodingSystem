import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TicketDetail } from './TicketDetail';
import type { Ticket, AiPlan, AiLog, TestResult } from '@/types';

/* ─── Test data ─── */
const mockTicket: Ticket = {
  id: 'ticket-1',
  project_id: 'proj-1',
  ticket_number: 42,
  title: 'Implement auth flow',
  description: 'Add login and register screens',
  priority: 'P1',
  column_name: 'ai_coding',
  position: 0,
  labels: ['auth', 'frontend'],
  retry_count: 0,
  created_at: '2026-03-20T10:00:00Z',
  updated_at: '2026-03-27T12:00:00Z',
};

const mockPlan: AiPlan = {
  id: 'plan-1',
  ticket_id: 'ticket-1',
  version: 1,
  agent_name: 'claude',
  plan_markdown: '## Plan\n1. Create LoginPage\n2. Add auth store',
  subtasks: [],
  file_list: ['src/LoginPage.tsx', 'src/authStore.ts'],
  status: 'approved',
  prompt_tokens: 100,
  completion_tokens: 200,
  cost_usd: 0.01,
  latency_ms: 1500,
  created_at: '2026-03-21T10:00:00Z',
};

const mockAiLog: AiLog = {
  id: 'log-1',
  ticket_id: 'ticket-1',
  agent_name: 'claude',
  action_type: 'plan_generation',
  model_id: 'claude-sonnet-4-6',
  prompt_tokens: 100,
  completion_tokens: 200,
  cost_usd: 0.005,
  latency_ms: 2000,
  status: 'success',
  created_at: '2026-03-21T10:00:00Z',
};

const mockTestResult: TestResult = {
  id: 'test-1',
  ticket_id: 'ticket-1',
  run_type: 'unit',
  tool_name: 'vitest',
  passed: true,
  total_tests: 15,
  passed_count: 14,
  failed_count: 1,
  skipped_count: 0,
  coverage_pct: 85,
  duration_ms: 5000,
  created_at: '2026-03-22T10:00:00Z',
};

/* ─── Mock store ─── */
const mockFetchTicket = vi.fn();
const mockFetchAttachments = vi.fn();
const mockFetchPlans = vi.fn();
const mockFetchAiLogs = vi.fn();
const mockFetchTestResults = vi.fn();
const mockFetchHistory = vi.fn();
const mockReset = vi.fn();

let storeState: Record<string, unknown> = {};

function resetStoreState() {
  storeState = {
    currentTicket: mockTicket,
    plans: [],
    codeGens: [],
    aiLogs: [],
    testResults: [],
    history: [],
    attachments: [],
    isLoading: false,
    error: null,
    fetchTicket: mockFetchTicket,
    fetchAttachments: mockFetchAttachments,
    fetchPlans: mockFetchPlans,
    fetchAiLogs: mockFetchAiLogs,
    fetchTestResults: mockFetchTestResults,
    fetchHistory: mockFetchHistory,
    reset: mockReset,
  };
}

vi.mock('@/stores/ticketStore', () => ({
  useTicketStore: vi.fn(() => storeState),
}));

/* ─── Mock comments API for TicketComments (uses react-query) ─── */
vi.mock('@/api/comments', () => ({
  listComments: vi.fn(() => Promise.resolve([])),
  createComment: vi.fn(),
  updateComment: vi.fn(),
  deleteComment: vi.fn(),
}));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function renderDetail() {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/tickets/ticket-1']}>
        <Routes>
          <Route path="/tickets/:id" element={<TicketDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TicketDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStoreState();
    queryClient.clear();
  });

  it('fetches ticket on mount', () => {
    renderDetail();
    expect(mockFetchTicket).toHaveBeenCalledWith('ticket-1');
  });

  it('calls reset on unmount', () => {
    const { unmount } = renderDetail();
    unmount();
    expect(mockReset).toHaveBeenCalled();
  });

  it('renders ticket title', () => {
    renderDetail();
    expect(screen.getByText('Implement auth flow')).toBeInTheDocument();
  });

  it('renders ticket description', () => {
    renderDetail();
    expect(screen.getByText('Add login and register screens')).toBeInTheDocument();
  });

  it('renders column badge', () => {
    renderDetail();
    expect(screen.getByText('AI Coding')).toBeInTheDocument();
  });

  it('renders priority badge', () => {
    renderDetail();
    expect(screen.getByText('P1 - High')).toBeInTheDocument();
  });

  it('renders labels', () => {
    renderDetail();
    expect(screen.getByText('auth')).toBeInTheDocument();
    expect(screen.getByText('frontend')).toBeInTheDocument();
  });

  it('renders all 7 tab buttons', () => {
    renderDetail();
    expect(screen.getByText('Comments')).toBeInTheDocument();
    expect(screen.getByText('Attachments')).toBeInTheDocument();
    expect(screen.getByText('Plan')).toBeInTheDocument();
    expect(screen.getByText('Code')).toBeInTheDocument();
    expect(screen.getByText('Tests')).toBeInTheDocument();
    expect(screen.getByText('AI Logs')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
  });

  it('shows Back to Board button', () => {
    renderDetail();
    expect(screen.getByText('Back to Board')).toBeInTheDocument();
  });

  it('shows spinner when loading', () => {
    storeState = { ...storeState, isLoading: true, currentTicket: null };
    const { container } = renderDetail();
    const spinner = container.querySelector('svg.animate-spin');
    expect(spinner).not.toBeNull();
  });

  it('shows error state', () => {
    storeState = { ...storeState, currentTicket: null, error: 'Not found' };
    renderDetail();
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Not found')).toBeInTheDocument();
  });

  /* ─── Tab switching & data fetching ─── */

  it('fetches plans when Plan tab is clicked', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Plan'));
    expect(mockFetchPlans).toHaveBeenCalledWith('ticket-1');
  });

  it('fetches AI logs when AI Logs tab is clicked', () => {
    renderDetail();
    fireEvent.click(screen.getByText('AI Logs'));
    expect(mockFetchAiLogs).toHaveBeenCalledWith('ticket-1');
  });

  it('fetches test results when Tests tab is clicked', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Tests'));
    expect(mockFetchTestResults).toHaveBeenCalledWith('ticket-1');
  });

  it('fetches history when History tab is clicked', () => {
    renderDetail();
    fireEvent.click(screen.getByText('History'));
    expect(mockFetchHistory).toHaveBeenCalledWith('ticket-1');
  });

  it('fetches attachments when Attachments tab is clicked', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Attachments'));
    expect(mockFetchAttachments).toHaveBeenCalledWith('ticket-1');
  });

  /* ─── Plan tab content ─── */

  it('shows empty state for plans tab', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Plan'));
    expect(screen.getByText('No AI plan generated yet.')).toBeInTheDocument();
  });

  it('renders plan data when available', () => {
    storeState = { ...storeState, plans: [mockPlan] };
    renderDetail();
    fireEvent.click(screen.getByText('Plan'));
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.getByText('src/LoginPage.tsx')).toBeInTheDocument();
  });

  /* ─── AI Logs tab content ─── */

  it('shows empty state for AI logs tab', () => {
    renderDetail();
    fireEvent.click(screen.getByText('AI Logs'));
    expect(screen.getByText('No AI logs yet.')).toBeInTheDocument();
  });

  it('renders AI log entries when available', () => {
    storeState = { ...storeState, aiLogs: [mockAiLog] };
    renderDetail();
    fireEvent.click(screen.getByText('AI Logs'));
    expect(screen.getByText('claude')).toBeInTheDocument();
    expect(screen.getByText('plan_generation')).toBeInTheDocument();
  });

  /* ─── Tests tab content ─── */

  it('shows empty state for tests tab', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Tests'));
    expect(screen.getByText('No test results yet.')).toBeInTheDocument();
  });

  it('renders test results when available', () => {
    storeState = { ...storeState, testResults: [mockTestResult] };
    renderDetail();
    fireEvent.click(screen.getByText('Tests'));
    // Badge shows "Passed", stats show passed_count
    const passedElements = screen.getAllByText('Passed');
    expect(passedElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  /* ─── Code tab content ─── */

  it('shows empty state for code tab', () => {
    renderDetail();
    fireEvent.click(screen.getByText('Code'));
    expect(screen.getByText('No code generations yet.')).toBeInTheDocument();
  });
});
