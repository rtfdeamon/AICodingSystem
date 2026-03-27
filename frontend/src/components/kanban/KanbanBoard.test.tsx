import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KanbanBoard } from './KanbanBoard';
import * as projectsApi from '@/api/projects';

/* ─── Mock stores ─── */
const mockFetchBoard = vi.fn();
const mockMoveTicket = vi.fn();
const mockSubscribeProject = vi.fn();
const mockUnsubscribeProject = vi.fn();

vi.mock('@/stores/kanbanStore', () => ({
  useKanbanStore: vi.fn(() => ({
    columns: {
      backlog: [],
      ai_planning: [],
      plan_review: [],
      ai_coding: [],
      code_review: [],
      staging: [],
      staging_verification: [],
      production: [],
    },
    isLoading: false,
    error: null,
    fetchBoard: mockFetchBoard,
    moveTicket: mockMoveTicket,
  })),
}));

vi.mock('@/stores/wsStore', () => ({
  useWSStore: vi.fn(() => ({
    subscribeProject: mockSubscribeProject,
    unsubscribeProject: mockUnsubscribeProject,
  })),
}));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { id: 'user-1', role: 'owner', full_name: 'Test User' },
  })),
}));

/* ─── Mock API ─── */
const mockProject = {
  id: 'proj-uuid-123',
  name: 'Test Project',
  description: 'A test project',
  repo_url: null,
  default_branch: 'main',
  creator_id: 'user-1',
  created_at: '2026-03-27T00:00:00Z',
  updated_at: '2026-03-27T00:00:00Z',
};

vi.mock('@/api/projects', () => ({
  listProjects: vi.fn(() =>
    Promise.resolve({ items: [mockProject], total: 1, page: 1, page_size: 50, pages: 1 }),
  ),
  createProject: vi.fn(() => Promise.resolve(mockProject)),
}));

function renderBoard() {
  return render(
    <MemoryRouter>
      <KanbanBoard />
    </MemoryRouter>,
  );
}

describe('KanbanBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to default successful response
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [mockProject],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    });
  });

  it('renders board header with project name after loading', async () => {
    renderBoard();
    await waitFor(() => {
      expect(screen.getByText('Test Project')).toBeInTheDocument();
    });
  });

  it('fetches board with project ID after init', async () => {
    renderBoard();
    await waitFor(() => {
      expect(mockFetchBoard).toHaveBeenCalledWith('proj-uuid-123');
    });
  });

  it('subscribes to WebSocket for project', async () => {
    renderBoard();
    await waitFor(() => {
      expect(mockSubscribeProject).toHaveBeenCalledWith('proj-uuid-123');
    });
  });

  it('renders all 8 kanban columns', async () => {
    renderBoard();
    await waitFor(() => {
      expect(screen.getByText('Backlog')).toBeInTheDocument();
    });
    expect(screen.getByText('AI Planning')).toBeInTheDocument();
    expect(screen.getByText('Plan Review')).toBeInTheDocument();
    expect(screen.getByText('AI Coding')).toBeInTheDocument();
    expect(screen.getByText('Code Review')).toBeInTheDocument();
    expect(screen.getByText('Staging')).toBeInTheDocument();
    expect(screen.getByText('Staging Verification')).toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
  });

  it('renders New Ticket button for owner role', async () => {
    renderBoard();
    await waitFor(() => {
      expect(screen.getByText('New Ticket')).toBeInTheDocument();
    });
  });

  it('auto-creates project when none exist', async () => {
    vi.mocked(projectsApi.listProjects).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
      pages: 0,
    });

    renderBoard();
    await waitFor(() => {
      expect(projectsApi.createProject).toHaveBeenCalledWith({
        name: 'My Project',
        description: 'Default project created automatically',
      });
    });
  });

  it('shows error state on project load failure', async () => {
    vi.mocked(projectsApi.listProjects).mockRejectedValue({
      response: { data: { detail: 'Server error' } },
    });

    renderBoard();
    await waitFor(() => {
      expect(screen.getByText('Error loading board')).toBeInTheDocument();
    });
    expect(screen.getByText('Server error')).toBeInTheDocument();
  });

  it('shows "No tickets" placeholder in empty columns', async () => {
    renderBoard();
    await waitFor(() => {
      const placeholders = screen.getAllByText('No tickets');
      expect(placeholders.length).toBe(8);
    });
  });

  it('renders Drag tickets helper text', async () => {
    renderBoard();
    await waitFor(() => {
      expect(
        screen.getByText('Drag tickets between columns to update their status'),
      ).toBeInTheDocument();
    });
  });
});
