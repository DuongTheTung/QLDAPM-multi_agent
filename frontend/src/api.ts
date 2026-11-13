import type { Project, ProjectAgent, ProjectDetail } from './types'

const ROOT = import.meta.env.VITE_API_URL || ''

async function json<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, options)
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`)
  return response.json()
}

export const api = {
  list: () => json<Project[]>('/api/projects'),
  get: (id: string) => json<ProjectDetail>(`/api/projects/${id}`),
  create: (prompt: string) => json<Project>('/api/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
  }),
  retry: (id: string) => json<{ status: string }>(`/api/projects/${id}/retry`, { method: 'POST' }),
  stop: (id: string) => json<{ status: string }>(`/api/projects/${id}/stop`, { method: 'POST' }),
  createAgent: (id: string, agent: { name: string; role: string; instructions: string; color: string }) => json<ProjectAgent>(`/api/projects/${id}/agents`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(agent),
  }),
  updateAgent: (id: string, agentId: string, changes: Partial<Pick<ProjectAgent, 'name' | 'role' | 'instructions' | 'color' | 'enabled'>>) => json<ProjectAgent>(`/api/projects/${id}/agents/${agentId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
  }),
  removeAgent: (id: string, agentId: string) => json<{ status: string; agent_id: string }>(`/api/projects/${id}/agents/${agentId}`, { method: 'DELETE' }),
  remove: (id: string) => json<{ status: string; project_id: string }>(`/api/projects/${id}`, { method: 'DELETE' }),
  artifact: (url: string) => `${ROOT}${url}`,
}

