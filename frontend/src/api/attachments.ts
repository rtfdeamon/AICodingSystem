import apiClient from './client';

export interface Attachment {
  id: string;
  ticket_id: string;
  uploader_id: string;
  filename: string;
  content_type: string;
  file_size: number;
  created_at: string;
}

export async function listAttachments(ticketId: string): Promise<{ items: Attachment[]; total: number }> {
  const { data } = await apiClient.get(`/tickets/${ticketId}/attachments`);
  return data;
}

export async function uploadAttachment(ticketId: string, file: File): Promise<Attachment> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post(`/tickets/${ticketId}/attachments`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function deleteAttachment(id: string): Promise<void> {
  await apiClient.delete(`/attachments/${id}`);
}

export function getDownloadUrl(id: string): string {
  return `/api/v1/attachments/${id}/download`;
}
