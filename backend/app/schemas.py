from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

AgentId = Literal["pm", "writer", "designer", "artist", "editor"]


class CreateProjectRequest(BaseModel):
    prompt: str = Field(min_length=12, max_length=6000)
    title: str | None = Field(default=None, max_length=120)


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    role: str = Field(min_length=2, max_length=100)
    instructions: str = Field(min_length=10, max_length=4000)
    color: str = Field(default="#557a68", pattern=r"^#[0-9a-fA-F]{6}$")


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    role: str | None = Field(default=None, min_length=2, max_length=100)
    instructions: str | None = Field(default=None, min_length=10, max_length=4000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enabled: bool | None = None


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


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

