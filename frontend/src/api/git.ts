import apiClient from './client';

export interface GitStatus {
  branch: string;
  ahead: number;
  behind: number;
  staged: string[];
  modified: string[];
  untracked: string[];
  conflicted: string[];
}

export interface GitDiff {
  files: {
    path: string;
    status: 'added' | 'modified' | 'deleted' | 'renamed';
    additions: number;
    deletions: number;
    diff: string;
  }[];
  total_additions: number;
  total_deletions: number;
}

export interface GitFile {
  path: string;
  type: 'file' | 'directory';
  size?: number;
  last_modified?: string;
}

export async function cloneRepo(payload: {
  url: string;
  branch?: string;
  ticket_id: string;
}): Promise<{ task_id: string; message: string }> {
  const { data } = await apiClient.post<{ task_id: string; message: string }>(
    '/git/clone',
    payload,
  );
  return data;
}

export async function getStatus(ticketId: string): Promise<GitStatus> {
  const { data } = await apiClient.get<GitStatus>(`/git/status/${ticketId}`);
  return data;
}

export async function getDiff(ticketId: string, params?: {
  base?: string;
  head?: string;
}): Promise<GitDiff> {
  const { data } = await apiClient.get<GitDiff>(`/git/diff/${ticketId}`, { params });
  return data;
}

export async function getFiles(ticketId: string, params?: {
  path?: string;
}): Promise<GitFile[]> {
  const { data } = await apiClient.get<GitFile[]>(`/git/files/${ticketId}`, { params });
  return data;
}
