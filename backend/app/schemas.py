from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

AgentId = Literal["pm", "writer", "designer", "artist", "reviewer", "editor"]
WorkerRole = Literal["writer", "designer", "artist", "reviewer", "editor"]

WORKER_ROLE_LABELS: dict[str, str] = {
    "writer": "Biên kịch",
    "designer": "Thiết kế nhân vật",
    "artist": "Họa sĩ",
    "reviewer": "Kiểm duyệt",
    "editor": "Biên tập & dàn trang",
}


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    role_key: WorkerRole
    instructions: str = Field(min_length=10, max_length=4000)
    color: str = Field(default="#557a68", pattern=r"^#[0-9a-fA-F]{6}$")
    model: str | None = Field(default=None, max_length=160)
    fallback_models: list[str] = Field(default_factory=list, max_length=8)
    image_model: str | None = Field(default=None, max_length=160)
    temperature: float | None = Field(default=None, ge=0, le=2)


class InitialCoreAgentModel(BaseModel):
    agent_id: AgentId
    model: str | None = Field(default=None, max_length=160)


class CreateProjectRequest(BaseModel):
    prompt: str = Field(min_length=12, max_length=6000)
    title: str | None = Field(default=None, max_length=120)
    agents: list[CreateAgentRequest] = Field(default_factory=list, max_length=10)
    core_agent_models: list[InitialCoreAgentModel] = Field(default_factory=list, max_length=6)


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    role: str | None = Field(default=None, min_length=2, max_length=100)
    role_key: WorkerRole | None = None
    instructions: str | None = Field(default=None, min_length=10, max_length=4000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enabled: bool | None = None
    model: str | None = Field(default=None, max_length=160)
    fallback_models: list[str] | None = Field(default=None, max_length=8)
    image_model: str | None = Field(default=None, max_length=160)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ProjectSettingsRequest(BaseModel):
    approval_enabled: bool
    approval_stages: list[Literal["script", "character_design", "illustration", "final"]] = []


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "revise"]
    feedback: str = Field(default="", max_length=4000)
    target_agent: Literal["writer", "designer", "artist", "reviewer", "editor"] | None = None


class InterventionRequest(BaseModel):
    event_id: int | None = None
    target_agent: Literal["writer", "designer", "artist", "reviewer", "editor"]
    feedback: str = Field(min_length=3, max_length=4000)


class UpdateContentRequest(BaseModel):
    content: Any


class RouterSettingsRequest(BaseModel):
    models: list[str] = Field(min_length=1, max_length=20)
    image_model: str = Field(min_length=2, max_length=160)


class ProjectSummary(BaseModel):
    id: str
    title: str
    prompt: str
    status: str
    stage: str
    progress: int
    created_at: str
    updated_at: str
    final_pdf: str | None = None
    error: str | None = None


class WorkflowTask(BaseModel):
    id: str
    project_id: str
    title: str
    agent: str
    status: str
    start_at: str
    due_at: str
    depends_on: list[str] = []
    detail: str = ""
    order_index: int = 0
    parent_id: str | None = None
    item_type: Literal["task", "subtask"] = "task"
    step_key: str = ""


class EventRecord(BaseModel):
    id: int
    project_id: str
    agent: str
    event_type: str
    message: str
    payload: dict[str, Any] = {}
    created_at: str


class ArtifactRecord(BaseModel):
    id: int
    project_id: str
    agent: str
    kind: str
    name: str
    path: str
    url: str
    created_at: str


class ComicState(TypedDict, total=False):
    project_id: str
    user_prompt: str
    title: str
    stage: str
    plan: dict[str, Any]
    script: dict[str, Any]
    character_bible: dict[str, Any]
    page_prompts: list[dict[str, Any]]
    page_images: list[str]
    cover_image: str
    review: dict[str, Any]
    revision_count: int
    revision_target: str
    feedback: str
    final_pdf: str
    completed: bool
    error: str
    model_usage: list[dict[str, Any]]
    custom_agent_outputs: list[dict[str, Any]]
    approved_signatures: list[str]
    automatic_revision_counts: dict[str, int]
    review_bypass: list[str]


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

