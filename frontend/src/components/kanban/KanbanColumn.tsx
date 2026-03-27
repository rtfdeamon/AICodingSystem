import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { clsx } from 'clsx';
import type { Ticket, ColumnName } from '@/types';
import { TicketCard } from './TicketCard';
import { COLUMN_LABELS, COLUMN_COLORS } from '@/utils/constants';
import { isHumanGateColumn } from '@/utils/permissions';
import { Shield } from 'lucide-react';

interface KanbanColumnProps {
  column: ColumnName;
  tickets: Ticket[];
}

export function KanbanColumn({ column, tickets }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: column,
    data: { column },
  });

  const color = COLUMN_COLORS[column];
  const isGate = isHumanGateColumn(column);

  return (
    <div
      className={clsx(
        'kanban-column shrink-0',
        isOver && 'ring-2 ring-brand-400 ring-offset-2',
      )}
    >
      {/* Column header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className="h-3 w-3 rounded-full"
            style={{ backgroundColor: color }}
          />
          <h3 className="text-sm font-semibold text-gray-700">
            {COLUMN_LABELS[column]}
          </h3>
          {isGate && (
            <Shield className="h-3.5 w-3.5 text-purple-500" />
          )}
        </div>
        <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-gray-200 px-1.5 text-[10px] font-bold text-gray-600">
          {tickets.length}
        </span>
      </div>

      {/* Droppable area */}
      <div
        ref={setNodeRef}
        className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-thin pb-2"
      >
        <SortableContext
          items={tickets.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          {tickets.map((ticket) => (
            <TicketCard key={ticket.id} ticket={ticket} />
          ))}
        </SortableContext>

        {tickets.length === 0 && (
          <div className="flex flex-1 items-center justify-center rounded-lg border-2 border-dashed border-gray-200 py-8">
            <p className="text-xs text-gray-400">No tickets</p>
          </div>
        )}
      </div>
    </div>
  );
}
