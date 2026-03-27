import { useNavigate } from 'react-router-dom';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Clock } from 'lucide-react';
import { clsx } from 'clsx';
import type { Ticket } from '@/types';
import { Badge } from '@/components/common/Badge';
import { Avatar } from '@/components/common/Avatar';
import { formatRelativeTime, formatPriority, truncateText } from '@/utils/formatters';

interface TicketCardProps {
  ticket: Ticket;
}

const priorityBadgeVariant: Record<string, 'danger' | 'warning' | 'default' | 'success'> = {
  P0: 'danger',
  P1: 'warning',
  P2: 'default',
  P3: 'success',
};

export function TicketCard({ ticket }: TicketCardProps) {
  const navigate = useNavigate();

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: ticket.id,
    data: { ticket },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        'kanban-card group',
        isDragging && 'opacity-50 shadow-lg ring-2 ring-brand-400',
      )}
      onClick={() => navigate(`/tickets/${ticket.id}`)}
    >
      {/* Header: drag handle + priority */}
      <div className="mb-2 flex items-start justify-between">
        <div className="flex items-center gap-1.5">
          <button
            className="cursor-grab text-gray-300 hover:text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity"
            {...attributes}
            {...listeners}
          >
            <GripVertical className="h-4 w-4" />
          </button>
          <Badge variant={priorityBadgeVariant[ticket.priority] ?? 'default'} dot>
            {formatPriority(ticket.priority)}
          </Badge>
        </div>
        {ticket.story_points != null && (
          <span className="text-[10px] font-semibold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">
            {ticket.story_points} pts
          </span>
        )}
      </div>

      {/* Title */}
      <h4 className="text-sm font-medium text-gray-900 leading-snug mb-1.5">
        {truncateText(ticket.title, 60)}
      </h4>

      {/* Description preview */}
      {ticket.description && (
        <p className="text-xs text-gray-500 mb-3 leading-relaxed">
          {truncateText(ticket.description, 80)}
        </p>
      )}

      {/* Labels */}
      {ticket.labels && ticket.labels.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {ticket.labels.slice(0, 3).map((label) => (
            <span
              key={label}
              className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600"
            >
              {label}
            </span>
          ))}
          {ticket.labels.length > 3 && (
            <span className="text-[10px] text-gray-400">
              +{ticket.labels.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Footer: assignee + time */}
      <div className="flex items-center justify-between">
        {ticket.assignee ? (
          <Avatar
            name={ticket.assignee.full_name}
            src={ticket.assignee.avatar_url}
            size="sm"
          />
        ) : (
          <div className="h-6 w-6 rounded-full border-2 border-dashed border-gray-300" />
        )}
        <div className="flex items-center gap-1 text-[10px] text-gray-400">
          <Clock className="h-3 w-3" />
          {formatRelativeTime(ticket.updated_at)}
        </div>
      </div>
    </div>
  );
}
