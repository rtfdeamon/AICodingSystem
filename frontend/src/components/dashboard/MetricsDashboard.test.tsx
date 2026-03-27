import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MetricsDashboard } from './MetricsDashboard';

/* ─── Mock kanbanStore ─── */
let mockProjectId: string | null = 'proj-uuid-123';

vi.mock('@/stores/kanbanStore', () => ({
  useKanbanStore: vi.fn((selector: (s: { currentProjectId: string | null }) => unknown) =>
    selector({ currentProjectId: mockProjectId }),
  ),
}));

/* ─── Mock dashboard API ─── */
const mockPipelineStats = vi.fn().mockResolvedValue({
  tickets_per_column: { backlog: 5, ai_planning: 2 },
  avg_time_per_column_hours: { backlog: 1.5 },
  total_tickets: 7,
});

const mockAiCosts = vi.fn().mockResolvedValue({
  cost_by_agent: { claude: 1.5 },
  cost_by_day: { '2026-03-27': 1.5 },
  total_cost: 1.5,
  tokens_total: 5000,
});

const mockCodeQuality = vi.fn().mockResolvedValue({
  lint_pass_rate: 0.95,
  test_coverage_avg: 87.5,
  review_pass_rate: 0.9,
  security_vuln_count: 0,
});

const mockDeploymentStats = vi.fn().mockResolvedValue({
  deploy_count: 12,
  rollback_rate: 0.083,
  avg_deploy_time_ms: 180000,
  success_rate: 0.917,
});

vi.mock('@/api/dashboard', () => ({
  pipelineStats: (...args: unknown[]) => mockPipelineStats(...args),
  aiCosts: (...args: unknown[]) => mockAiCosts(...args),
  codeQuality: (...args: unknown[]) => mockCodeQuality(...args),
  deploymentStats: (...args: unknown[]) => mockDeploymentStats(...args),
}));

describe('MetricsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProjectId = 'proj-uuid-123';
  });

  it('passes real project ID (not hardcoded "default") to API calls', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(mockPipelineStats).toHaveBeenCalledWith({ project_id: 'proj-uuid-123' });
      expect(mockAiCosts).toHaveBeenCalledWith({ project_id: 'proj-uuid-123' });
      expect(mockCodeQuality).toHaveBeenCalledWith({ project_id: 'proj-uuid-123' });
      expect(mockDeploymentStats).toHaveBeenCalledWith({ project_id: 'proj-uuid-123' });
    });
  });

  it('never sends project_id="default"', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(mockPipelineStats).toHaveBeenCalled();
    });
    for (const mock of [mockPipelineStats, mockAiCosts, mockCodeQuality, mockDeploymentStats]) {
      const calls = mock.mock.calls;
      for (const call of calls) {
        expect(call[0].project_id).not.toBe('default');
      }
    }
  });

  it('shows error when no project is selected', async () => {
    mockProjectId = null;
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/No project selected/)).toBeInTheDocument();
    });
    expect(mockPipelineStats).not.toHaveBeenCalled();
  });

  it('renders Dashboard heading', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });

  it('renders overview metrics after loading', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Total Tickets')).toBeInTheDocument();
    });
    // Verify the metric values rendered
    await waitFor(() => {
      expect(screen.getByText('7')).toBeInTheDocument();
    });
  });

  it('renders all tab buttons', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });
    expect(screen.getByText('Pipeline')).toBeInTheDocument();
    expect(screen.getByText('AI Costs')).toBeInTheDocument();
    expect(screen.getByText('Code Quality')).toBeInTheDocument();
    expect(screen.getByText('Deployments')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('shows error state when API fails', async () => {
    mockPipelineStats.mockRejectedValue({
      response: { data: { message: 'Internal server error' } },
    });
    render(<MetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Error')).toBeInTheDocument();
    });
  });
});
