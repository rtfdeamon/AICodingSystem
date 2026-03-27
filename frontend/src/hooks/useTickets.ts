import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as ticketsApi from '@/api/tickets';
import * as commentsApi from '@/api/comments';
import type { Ticket, Comment } from '@/types';

export function useTicketList(projectId: string, params: ticketsApi.TicketListParams = {}) {
  return useQuery({
    queryKey: ['tickets', projectId, params],
    queryFn: () => ticketsApi.listTickets(projectId, params),
    enabled: !!projectId,
  });
}

export function useTicket(id: string | undefined) {
  return useQuery({
    queryKey: ['tickets', id],
    queryFn: () => ticketsApi.getTicket(id!),
    enabled: !!id,
  });
}

export function useCreateTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ticketsApi.CreateTicketPayload & { project_id: string }) => {
      const { project_id, ...rest } = payload;
      return ticketsApi.createTicket(project_id, rest);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] });
    },
  });
}

export function useUpdateTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ticketsApi.UpdateTicketPayload }) =>
      ticketsApi.updateTicket(id, payload),
    onSuccess: (ticket: Ticket) => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] });
      queryClient.setQueryData(['tickets', ticket.id], ticket);
    },
  });
}

export function useDeleteTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => ticketsApi.deleteTicket(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] });
    },
  });
}

/* ─── Comments ─── */
export function useComments(ticketId: string | undefined) {
  return useQuery({
    queryKey: ['comments', ticketId],
    queryFn: () => commentsApi.listComments(ticketId!),
    enabled: !!ticketId,
  });
}

export function useCreateComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: commentsApi.CreateCommentPayload) =>
      commentsApi.createComment(payload),
    onSuccess: (comment: Comment) => {
      queryClient.invalidateQueries({ queryKey: ['comments', comment.ticket_id] });
    },
  });
}

export function useUpdateComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      commentsApi.updateComment(id, { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments'] });
    },
  });
}

export function useDeleteComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => commentsApi.deleteComment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments'] });
    },
  });
}
