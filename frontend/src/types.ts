export type AgentId = 'pm' | 'writer' | 'designer' | 'artist' | 'editor'

export interface Project {
  id: string; title: string; prompt: string; status: string; stage: string; progress: number
  created_at: string; updated_at: string; final_pdf?: string; error?: string
}

export interface Task {
  id: string; title: string; agent: string; status: string; start_at: string; due_at: string
  depends_on: string[]; detail: string; order_index: number
}

export interface EventItem {
  id: number; agent: string; event_type: string; message: string; payload: Record<string, unknown>; created_at: string
}

export interface Artifact {
  id: number; agent: string; kind: string; name: string; path: string; url: string; created_at: string
}

export interface ProjectAgent {
  id: string; key: string; project_id: string; name: string; role: string; instructions: string
  color: string; is_core: boolean; enabled: boolean; created_at: string
}

export interface ProjectDetail extends Project {
  tasks: Task[]; events: EventItem[]; artifacts: Artifact[]; agents: ProjectAgent[]
}

