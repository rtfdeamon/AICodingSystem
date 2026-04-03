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
  const [businessTask, setBusinessTask] = useState('');
  const [decomposedTask, setDecomposedTask] = useState('');
  const [codingTask, setCodingTask] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
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
        business_task: businessTask || undefined,
        decomposed_task: decomposedTask || undefined,
        coding_task: codingTask || undefined,
        ai_prompt: aiPrompt || undefined,
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
            rows={2}
            className="input resize-none mb-3"
          />
        </div>

        <div>
           <label htmlFor="business_task" className="mb-1.5 block text-sm font-medium text-gray-700">
              Общая бизнес задача
           </label>
           <textarea
              id="business_task"
              value={businessTask}
              onChange={(e) => setBusinessTask(e.target.value)}
              placeholder="Business context and goals..."
              rows={2}
              className="input resize-none mb-3"
           />
        </div>

        <div>
           <label htmlFor="decomposed_task" className="mb-1.5 block text-sm font-medium text-gray-700">
              Декомпозированная задача
           </label>
           <textarea
              id="decomposed_task"
              value={decomposedTask}
              onChange={(e) => setDecomposedTask(e.target.value)}
              placeholder="Break down of the task..."
              rows={2}
              className="input resize-none mb-3"
           />
        </div>

        <div>
           <label htmlFor="coding_task" className="mb-1.5 block text-sm font-medium text-gray-700">
              Задача на кодирование
           </label>
           <textarea
              id="coding_task"
              value={codingTask}
              onChange={(e) => setCodingTask(e.target.value)}
              placeholder="Specific coding instructions..."
              rows={2}
              className="input resize-none mb-3"
           />
        </div>

        <div>
           <label htmlFor="ai_prompt" className="mb-1.5 block text-sm font-medium text-gray-700">
              ИИ промпт
           </label>
           <textarea
              id="ai_prompt"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="AI prompt text..."
              rows={2}
              className="input resize-none mb-3"
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
