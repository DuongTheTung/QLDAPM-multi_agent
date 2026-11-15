export type AgentId = 'pm' | 'writer' | 'designer' | 'artist' | 'reviewer' | 'editor'

export interface Project {
  id: string; title: string; prompt: string; status: string; stage: string; progress: number
  created_at: string; updated_at: string; final_pdf?: string; error?: string
  pause_requested: boolean; approval_enabled: boolean; approval_stages: ApprovalStage[]
}

export interface Task {
  id: string; title: string; agent: string; status: string; start_at: string; due_at: string
  depends_on: string[]; detail: string; order_index: number
  parent_id?: string; item_type?: 'task' | 'subtask'; step_key?: string
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
  model?: string; fallback_models: string[]; image_model?: string; temperature?: number
}

export type ApprovalStage = 'script' | 'character_design' | 'illustration' | 'final'

export interface Approval {
  id: number; project_id: string; stage: ApprovalStage; signature: string
  status: 'pending' | 'approved' | 'revision_requested'; content: Record<string, unknown>
  event_id?: number; feedback: string; assigned_agent?: string; created_at: string; resolved_at?: string
}

export interface Intervention {
  id: number; action: string; target_agent?: string; content_key?: string; feedback: string; created_at: string
}

export interface QualityTest {
  id: number; owner_agent: string; reviewer_agent: string; unit_key: string; title: string
  status: 'testing' | 'completed'; verdict?: 'PASS' | 'REVISE'; feedback: string
  artifact_ids: number[]; created_at: string; resolved_at?: string
}

export interface EventContent {
  event: EventItem; content_key?: string; content: unknown; artifacts: Artifact[]
  approval?: Approval; editable: boolean; can_intervene: boolean
}

export interface ProjectDetail extends Project {
  tasks: Task[]; events: EventItem[]; artifacts: Artifact[]; agents: ProjectAgent[]
  approvals: Approval[]; interventions: Intervention[]; quality_tests: QualityTest[]
}

