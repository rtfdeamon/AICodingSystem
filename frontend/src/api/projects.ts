import apiClient from './client';

export interface Project {
  id: string;
  name: string;
  description: string;
  repo_url: string | null;
  default_branch: string;
  creator_id: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export async function listProjects(): Promise<ProjectListResponse> {
  const { data } = await apiClient.get<ProjectListResponse>('/projects');
  return data;
}

export async function createProject(payload: {
  name: string;
  description?: string;
  repo_url?: string;
  default_branch?: string;
}): Promise<Project> {
  const { data } = await apiClient.post<Project>('/projects', payload);
  return data;
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await apiClient.get<Project>(`/projects/${id}`);
  return data;
}

export async function updateProject(
  id: string,
  payload: {
    name?: string;
    description?: string;
    repo_url?: string;
    default_branch?: string;
  },
): Promise<Project> {
  const { data } = await apiClient.put<Project>(`/projects/${id}`, payload);
  return data;
}
