import { useState, FormEvent } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { useCreateTicket } from '@/hooks/useTickets';
import { useKanbanStore } from '@/stores/kanbanStore';
import type { TicketPriority } from '@/types';

interface TicketFormProps {
  projectId: string;
  onClose: () => void;
}

export function TicketForm({ projectId, onClose }: TicketFormProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TicketPriority>('P2');
  const [labels, setLabels] = useState('');
  const [storyPoints, setStoryPoints] = useState('');

  const createTicket = useCreateTicket();
  const addTicket = useKanbanStore((s) => s.addTicket);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const ticket = await createTicket.mutateAsync({
        project_id: projectId,
        title,
        description: description || undefined,
        priority,
        labels: labels
          .split(',')
          .map((l) => l.trim())
          .filter(Boolean),
      });
      addTicket(ticket);
      onClose();
    } catch {
      // error handled by mutation
    }
  };

  return (
    <Modal open onClose={onClose} title="Create Ticket" maxWidth="max-w-xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        {createTicket.isError && (
          <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            Failed to create ticket. Please try again.
          </div>
        )}

        <div>
          <label htmlFor="title" className="mb-1.5 block text-sm font-medium text-gray-700">
            Title
          </label>
          <input
            id="title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Brief description of the task"
            className="input"
          />
        </div>

        <div>
          <label htmlFor="description" className="mb-1.5 block text-sm font-medium text-gray-700">
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Detailed requirements, acceptance criteria..."
            rows={4}
            className="input resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="priority" className="mb-1.5 block text-sm font-medium text-gray-700">
              Priority
            </label>
            <select
              id="priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TicketPriority)}
              className="input"
            >
              <option value="P0">P0 - Critical</option>
              <option value="P1">P1 - High</option>
              <option value="P2">P2 - Medium</option>
              <option value="P3">P3 - Low</option>
            </select>
          </div>

          <div>
            <label htmlFor="points" className="mb-1.5 block text-sm font-medium text-gray-700">
              Story Points
            </label>
            <input
              id="points"
              type="number"
              min="1"
              max="100"
              value={storyPoints}
              onChange={(e) => setStoryPoints(e.target.value)}
              placeholder="e.g. 5"
              className="input"
            />
          </div>
        </div>

        <div>
          <label htmlFor="labels" className="mb-1.5 block text-sm font-medium text-gray-700">
            Labels
          </label>
          <input
            id="labels"
            type="text"
            value={labels}
            onChange={(e) => setLabels(e.target.value)}
            placeholder="frontend, api, bug (comma-separated)"
            className="input"
          />
        </div>

        <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={createTicket.isPending}>
            Create Ticket
          </Button>
        </div>
      </form>
    </Modal>
  );
}
