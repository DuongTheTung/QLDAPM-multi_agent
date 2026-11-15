import type { AgentId, ApprovalStage, EventContent, Project, ProjectAgent, ProjectDetail, WorkerRole } from './types'

const ROOT = import.meta.env.VITE_API_URL || ''

type AgentChanges = Partial<Pick<ProjectAgent, 'name' | 'role' | 'instructions' | 'color' | 'enabled'>> & {
  model?: string | null; fallback_models?: string[] | null; image_model?: string | null; temperature?: number | null
}

export interface ModelCatalog {
  models: string[]; image_model: string
}

export interface RouterCatalog extends ModelCatalog {
  router: string; api_key_configured: boolean; available_models: string[]; catalog_error?: string
}

export interface CreateAgentInput {
  name: string; role_key: WorkerRole; instructions: string; color: string
  model?: string | null; fallback_models?: string[]; image_model?: string | null
  temperature?: number | null
}

export interface CoreAgentModelInput {
  agent_id: AgentId; model?: string | null
}

async function json<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, options)
  if (!response.ok) {
    const raw = await response.text()
    try { throw new Error(JSON.parse(raw).detail || raw || `HTTP ${response.status}`) }
    catch (error) { if (error instanceof SyntaxError) throw new Error(raw || `HTTP ${response.status}`); throw error }
  }
  return response.json()
}

export const api = {
  models: () => json<ModelCatalog>('/api/health'),
  routerModels: () => json<RouterCatalog>('/api/router/models'),
  updateRouterModels: (models: string[], image_model: string) => json<RouterCatalog>('/api/router/models', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ models, image_model }),
  }),
  list: () => json<Project[]>('/api/projects'),
  get: (id: string) => json<ProjectDetail>(`/api/projects/${id}`),
  create: (prompt: string, agents: CreateAgentInput[] = [], core_agent_models: CoreAgentModelInput[] = []) => json<Project>('/api/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt, agents, core_agent_models }),
  }),
  retry: (id: string) => json<{ status: string }>(`/api/projects/${id}/retry`, { method: 'POST' }),
  pause: (id: string) => json<{ status: string }>(`/api/projects/${id}/pause`, { method: 'POST' }),
  resume: (id: string) => json<{ status: string }>(`/api/projects/${id}/resume`, { method: 'POST' }),
  stop: (id: string) => json<{ status: string }>(`/api/projects/${id}/stop`, { method: 'POST' }),
  createAgent: (id: string, agent: CreateAgentInput) => json<ProjectAgent>(`/api/projects/${id}/agents`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(agent),
  }),
  updateAgent: (id: string, agentId: string, changes: AgentChanges) => json<ProjectAgent>(`/api/projects/${id}/agents/${agentId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
  }),
  removeAgent: (id: string, agentId: string) => json<{ status: string; agent_id: string }>(`/api/projects/${id}/agents/${agentId}`, { method: 'DELETE' }),
  remove: (id: string) => json<{ status: string; project_id: string }>(`/api/projects/${id}`, { method: 'DELETE' }),
  updateSettings: (id: string, approval_enabled: boolean, approval_stages: ApprovalStage[]) => json<Project>(`/api/projects/${id}/settings`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approval_enabled, approval_stages }),
  }),
  eventContent: (id: string, eventId: number) => json<EventContent>(`/api/projects/${id}/events/${eventId}/content`),
  updateEventContent: (id: string, eventId: number, content: unknown) => json<{ status: string }>(`/api/projects/${id}/events/${eventId}/content`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }),
  }),
  decideApproval: (id: string, approvalId: number, decision: 'approve' | 'revise', feedback = '', target_agent?: string) => json<{ status: string }>(`/api/projects/${id}/approvals/${approvalId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, feedback, target_agent }),
  }),
  intervene: (id: string, event_id: number, target_agent: string, feedback: string) => json<{ status: string }>(`/api/projects/${id}/interventions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_id, target_agent, feedback }),
  }),
  artifact: (url: string) => `${ROOT}${url}`,
}

