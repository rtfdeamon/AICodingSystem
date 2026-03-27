import { useEffect, useState, useCallback } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
} from '@dnd-kit/core';
import { Plus } from 'lucide-react';
import { useKanbanStore } from '@/stores/kanbanStore';
import { useWSStore } from '@/stores/wsStore';
import { useAuth } from '@/hooks/useAuth';
import { KanbanColumn } from './KanbanColumn';
import { TicketCard } from './TicketCard';
import { TicketForm } from '@/components/tickets/TicketForm';
import { Button } from '@/components/common/Button';
import { Spinner } from '@/components/common/Spinner';
import { COLUMN_NAMES } from '@/utils/constants';
import { canMoveToColumn, canCreateTicket } from '@/utils/permissions';
import { listProjects, createProject, type Project } from '@/api/projects';
import type { Ticket, ColumnName } from '@/types';

export function KanbanBoard() {
  const { columns, isLoading, error, fetchBoard, moveTicket } = useKanbanStore();
  const { user } = useAuth();
  const { subscribeProject, unsubscribeProject } = useWSStore();

  const [activeTicket, setActiveTicket] = useState<Ticket | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
  );

  // Load or create project on mount
  useEffect(() => {
    let cancelled = false;
    async function initProject() {
      setProjectLoading(true);
      setProjectError(null);
      try {
        const res = await listProjects();
        if (cancelled) return;
        if (res.items.length > 0) {
          setCurrentProject(res.items[0]);
          fetchBoard(res.items[0].id);
          subscribeProject(res.items[0].id);
        } else {
          // Auto-create default project
          const newProject = await createProject({
            name: 'My Project',
            description: 'Default project created automatically',
          });
          if (cancelled) return;
          setCurrentProject(newProject);
          fetchBoard(newProject.id);
          subscribeProject(newProject.id);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Failed to load projects';
        setProjectError(msg);
      } finally {
        if (!cancelled) setProjectLoading(false);
      }
    }
    initProject();
    return () => { cancelled = true; };
  }, [fetchBoard, subscribeProject]);

  // Clean up WebSocket subscription on unmount
  useEffect(() => {
    return () => {
      if (currentProject) {
        unsubscribeProject(currentProject.id);
      }
    };
  }, [currentProject, unsubscribeProject]);

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const ticket = event.active.data.current?.ticket as Ticket | undefined;
      if (ticket) setActiveTicket(ticket);
    },
    [],
  );

  const handleDragOver = useCallback((_event: DragOverEvent) => {}, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveTicket(null);
      const { active, over } = event;
      if (!over || !user) return;

      const ticket = active.data.current?.ticket as Ticket | undefined;
      if (!ticket) return;

      let targetColumn: ColumnName;
      if (over.data.current?.column) {
        targetColumn = over.data.current.column as ColumnName;
      } else if (over.data.current?.ticket) {
        targetColumn = (over.data.current.ticket as Ticket).column_name;
      } else {
        return;
      }

      if (ticket.column_name === targetColumn) return;

      if (!canMoveToColumn(user.role, ticket.column_name, targetColumn)) {
        return;
      }

      moveTicket(ticket.id, targetColumn);
    },
    [user, moveTicket],
  );

  if (projectLoading || isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (projectError || error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-lg font-semibold text-red-600">Error loading board</p>
          <p className="mt-1 text-sm text-gray-500">{projectError || error}</p>
          <Button
            variant="secondary"
            className="mt-4"
            onClick={() => window.location.reload()}
          >
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Board header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {currentProject?.name || 'Board'}
          </h1>
          <p className="text-sm text-gray-500">
            Drag tickets between columns to update their status
          </p>
        </div>
        {user && canCreateTicket(user.role) && (
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            New Ticket
          </Button>
        )}
      </div>

      {/* Columns */}
      <div className="flex-1 overflow-x-auto scrollbar-thin">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          <div className="flex gap-4 pb-4" style={{ minWidth: 'max-content' }}>
            {COLUMN_NAMES.map((col) => (
              <KanbanColumn
                key={col}
                column={col}
                tickets={columns[col] || []}
              />
            ))}
          </div>

          <DragOverlay>
            {activeTicket ? (
              <div className="rotate-3 opacity-90">
                <TicketCard ticket={activeTicket} />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>

      {/* Create ticket modal */}
      {showCreateForm && currentProject && (
        <TicketForm
          projectId={currentProject.id}
          onClose={() => setShowCreateForm(false)}
        />
      )}
    </div>
  );
}
