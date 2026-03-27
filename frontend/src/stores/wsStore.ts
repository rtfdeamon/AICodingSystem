import { create } from 'zustand';
import { wsManager } from '@/api/ws';
import { useKanbanStore } from './kanbanStore';
import { useTicketStore } from './ticketStore';
import { useNotificationStore } from './notificationStore';
import { WS_EVENTS } from '@/utils/constants';
import type { WSEvent, Ticket, Comment, Notification } from '@/types';

interface WSState {
  connected: boolean;
  reconnecting: boolean;
  connect: (token: string, projectId?: string) => void;
  disconnect: () => void;
  subscribeProject: (projectId: string) => void;
  unsubscribeProject: (projectId: string) => void;
}

export const useWSStore = create<WSState>((set) => ({
  connected: false,
  reconnecting: false,

  connect: (token, projectId) => {
    wsManager.connect(token);

    // Track connection state via global handler
    wsManager.on('*', () => {
      set({
        connected: wsManager.connected,
        reconnecting: wsManager.reconnecting,
      });
    });

    // Ticket events -> kanban store
    wsManager.on(WS_EVENTS.TICKET_CREATED, (event: WSEvent) => {
      const ticket = event.data as Ticket;
      useKanbanStore.getState().addTicket(ticket);
    });

    wsManager.on(WS_EVENTS.TICKET_UPDATED, (event: WSEvent) => {
      const ticket = event.data as Ticket;
      useKanbanStore.getState().updateTicket(ticket);
      const current = useTicketStore.getState().currentTicket;
      if (current?.id === ticket.id) {
        useTicketStore.getState().setCurrentTicket(ticket);
      }
    });

    wsManager.on(WS_EVENTS.TICKET_MOVED, (event: WSEvent) => {
      const ticket = event.data as Ticket;
      useKanbanStore.getState().updateTicket(ticket);
      const current = useTicketStore.getState().currentTicket;
      if (current?.id === ticket.id) {
        useTicketStore.getState().setCurrentTicket(ticket);
      }
    });

    wsManager.on(WS_EVENTS.TICKET_DELETED, (event: WSEvent) => {
      const { id } = event.data as { id: string };
      useKanbanStore.getState().removeTicket(id);
    });

    // Comment events -> ticket store
    wsManager.on(WS_EVENTS.COMMENT_ADDED, (event: WSEvent) => {
      const comment = event.data as Comment;
      useTicketStore.getState().addComment(comment);
    });

    wsManager.on(WS_EVENTS.COMMENT_UPDATED, (event: WSEvent) => {
      const comment = event.data as Comment;
      useTicketStore.getState().updateComment(comment);
    });

    wsManager.on(WS_EVENTS.COMMENT_DELETED, (event: WSEvent) => {
      const { id } = event.data as { id: string };
      useTicketStore.getState().removeComment(id);
    });

    // Notifications
    wsManager.on(WS_EVENTS.NOTIFICATION, (event: WSEvent) => {
      const notif = event.data as Notification;
      useNotificationStore.getState().addNotification(notif);
    });

    // Auto-subscribe to project if provided
    if (projectId) {
      wsManager.send({ type: 'subscribe_project', project_id: projectId });
    }

    // Don't optimistically set connected — let the global handler track real state
  },

  disconnect: () => {
    wsManager.disconnect();
    set({ connected: false, reconnecting: false });
  },

  subscribeProject: (projectId: string) => {
    wsManager.send({ type: 'subscribe_project', project_id: projectId });
  },

  unsubscribeProject: (projectId: string) => {
    wsManager.send({ type: 'unsubscribe_project', project_id: projectId });
  },
}));
