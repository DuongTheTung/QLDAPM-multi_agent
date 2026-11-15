from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError

from .agents.pm import PMAgent
from .config import get_settings
from .manager import WorkflowManager
from .runtime import db
from .schemas import (
    WORKER_ROLE_LABELS,
    ApprovalDecisionRequest,
    CreateAgentRequest,
    CreateProjectRequest,
    InterventionRequest,
    ProjectSettingsRequest,
    RouterSettingsRequest,
    UpdateAgentRequest,
    UpdateContentRequest,
)
from .workflow import ComicWorkflow

settings = get_settings()
workflow = ComicWorkflow(db, settings)
manager = WorkflowManager(db, workflow)


def load_router_settings() -> None:
    saved = db.get_app_setting("nine_router")
    if not isinstance(saved, dict):
        return
    models = saved.get("models")
    image_model = saved.get("image_model")
    if isinstance(models, list) and any(str(model).strip() for model in models):
        settings.nine_router_models = ",".join(
            str(model).strip() for model in models if str(model).strip()
        )
    if isinstance(image_model, str) and image_model.strip():
        settings.nine_router_image_model = image_model.strip()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    load_router_settings()
    migrate_legacy_task_lists()
    migrate_reviewer_tasks()
    manager.resume_pending()
    yield


app = FastAPI(title="ComicFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/artifacts", StaticFiles(directory=settings.artifacts_dir), name="artifacts")


def public_project(project: dict) -> dict:
    return {key: value for key, value in project.items() if key != "state_json"}


def artifact_url(path: str) -> str:
    try:
        relative = Path(path).resolve().relative_to(settings.artifacts_dir.resolve())
        return "/artifacts/" + relative.as_posix()
    except ValueError:
        return ""


def load_state(project: dict) -> dict:
    state = json.loads(project.get("state_json") or "{}")
    if state:
        return state
    return {
        "project_id": project["id"], "user_prompt": project["prompt"],
        "title": project["title"], "stage": project["stage"],
        "revision_count": 0, "model_usage": [], "completed": False,
    }


def event_content_key(agent: str) -> str | None:
    return {
        "pm": "plan", "writer": "script", "designer": "character_bible",
        "artist": "page_prompts", "reviewer": "review", "editor": None,
    }.get(agent)


def revision_stage(agent: str) -> str:
    return {
        "writer": "script", "designer": "character_design",
        "artist": "illustration", "reviewer": "testing", "editor": "layout",
    }[agent]


def validate_model_choices(changes: dict) -> None:
    model = str(changes.get("model") or "").strip()
    fallbacks = changes.get("fallback_models") or []
    image_model = str(changes.get("image_model") or "").strip()
    if model and model not in settings.models:
        raise HTTPException(422, "Model chính không nằm trong danh sách 9Router đã cấu hình")
    if any(item not in settings.models for item in fallbacks):
        raise HTTPException(422, "Model dự phòng không nằm trong danh sách 9Router đã cấu hình")
    if image_model and image_model != settings.nine_router_image_model:
        raise HTTPException(422, "Model ảnh không nằm trong danh sách đã cấu hình")


def migrate_legacy_task_lists() -> None:
    """Expand pre-hierarchy project plans without losing their progress or revision tickets."""
    for project in db.list_projects():
        existing = db.get_tasks(project["id"])
        if not existing or any(item.get("item_type") == "subtask" for item in existing):
            continue
        state = load_state(project)
        plan = state.get("plan", {})
        page_count = int(plan.get("page_count") or len(state.get("script", {}).get("pages", [])) or 8)
        custom_agents = db.list_project_agents(
            project["id"], custom_only=True, enabled_only=True,
        )
        expanded = workflow.pm._schedule(project["id"], page_count, custom_agents)
        base_items = [item for item in existing if not item["id"].startswith("REV-")]
        agent_status: dict[str, str] = {}
        for item in base_items:
            current = agent_status.get(item["agent"], "todo")
            if item["status"] == "in_progress" or current == "in_progress":
                agent_status[item["agent"]] = "in_progress"
            elif item["status"] == "done" and current == "todo":
                agent_status[item["agent"]] = "done"
        active_child_seen: set[str] = set()
        for item in expanded:
            status = agent_status.get(item["agent"], "todo")
            if status == "done":
                item["status"] = "done"
            elif status == "in_progress":
                if item["item_type"] == "task":
                    item["status"] = "in_progress"
                elif item["agent"] not in active_child_seen:
                    item["status"] = "in_progress"
                    active_child_seen.add(item["agent"])
        for revision in (item for item in existing if item["id"].startswith("REV-")):
            expanded.append({
                **revision, "parent_id": None, "item_type": "task", "step_key": "revision",
                "order_index": len(expanded),
            })
        db.replace_tasks(project["id"], expanded)


def migrate_reviewer_tasks() -> None:
    """Add the independent reviewer lane to projects created before six-agent workflows."""
    for project in db.list_projects():
        existing = db.get_tasks(project["id"])
        if not existing or any(
            item["agent"] == "reviewer" and item["item_type"] == "task" for item in existing
        ):
            continue
        state = load_state(project)
        page_count = int(
            state.get("plan", {}).get("page_count")
            or len(state.get("script", {}).get("pages", []))
            or 8
        )
        template = PMAgent._schedule(project["id"], page_count)
        replacement = [
            item for item in template if item["agent"] in {"reviewer", "editor"}
        ]
        completed = project["status"] == "completed" or project["stage"] == "finalized"
        reviewer_done = completed or project["stage"] == "layout"
        for item in replacement:
            if completed or (item["agent"] == "reviewer" and reviewer_done):
                item["status"] = "done"
        merged = [item for item in existing if item["agent"] != "editor"] + replacement
        for index, item in enumerate(merged):
            item["order_index"] = index
        db.replace_tasks(project["id"], merged)


@app.get("/api/health")
async def health():
    return {
        "status": "ok", "router": settings.nine_router_base_url,
        "models": settings.models, "image_model": settings.nine_router_image_model,
        "api_key_configured": bool(settings.nine_router_api_key),
    }


@app.get("/api/router/models")
async def get_router_models():
    available: list[str] = []
    catalog_error = ""
    if settings.nine_router_api_key:
        try:
            catalog = await asyncio.wait_for(workflow.router.client.models.list(), timeout=8)
            available = [str(item.id).strip() for item in catalog.data if str(item.id).strip()]
        except (APIError, TimeoutError) as error:
            catalog_error = str(error)[:300]
    else:
        catalog_error = "NINE_ROUTER_API_KEY chưa được cấu hình"
    configured = settings.models
    available = list(dict.fromkeys([*configured, settings.nine_router_image_model, *available]))
    return {
        "router": settings.nine_router_base_url,
        "api_key_configured": bool(settings.nine_router_api_key),
        "models": configured,
        "available_models": available,
        "image_model": settings.nine_router_image_model,
        "catalog_error": catalog_error or None,
    }


@app.put("/api/router/models")
async def update_router_models(request: RouterSettingsRequest):
    models = list(dict.fromkeys(model.strip() for model in request.models if model.strip()))
    image_model = request.image_model.strip()
    if not models:
        raise HTTPException(422, "Cần ít nhất một model văn bản")
    settings.nine_router_models = ",".join(models)
    settings.nine_router_image_model = image_model
    db.set_app_setting("nine_router", {"models": models, "image_model": image_model})
    return {
        "router": settings.nine_router_base_url,
        "api_key_configured": bool(settings.nine_router_api_key),
        "models": models,
        "available_models": list(dict.fromkeys([*models, image_model])),
        "image_model": image_model,
        "catalog_error": None,
    }


@app.post("/api/projects", status_code=202)
async def create_project(request: CreateProjectRequest):
    for core_config in request.core_agent_models:
        validate_model_choices({"model": core_config.model})
    for agent in request.agents:
        validate_model_choices({
            "model": agent.model, "fallback_models": agent.fallback_models,
            "image_model": agent.image_model, "temperature": agent.temperature,
        })
    project_id = uuid.uuid4().hex
    title = request.title or "Đang phân tích brief…"
    project = db.create_project(project_id, title, request.prompt.strip())
    for core_config in request.core_agent_models:
        db.update_project_agent(
            project_id, f"{project_id}:{core_config.agent_id}", model=core_config.model,
        )
    for agent_request in request.agents:
        agent = db.create_project_agent(
            project_id, agent_request.name.strip(), agent_request.role_key,
            agent_request.instructions.strip(), agent_request.color,
            agent_request.model, list(dict.fromkeys(agent_request.fallback_models)),
            agent_request.temperature, agent_request.image_model,
        )
        db.add_event(
            project_id, "pm", "agent_added",
            f"Đội hình ban đầu có {agent['name']} — {agent['role']}",
            {"agent_id": agent["id"], "during_project_creation": True},
        )
    initial_state = {
        "project_id": project_id, "user_prompt": request.prompt.strip(), "title": title,
        "stage": "brief", "revision_count": 0, "model_usage": [], "completed": False,
    }
    db.update_project(project_id, state_json=json.dumps(initial_state, ensure_ascii=False))
    db.add_event(project_id, "user", "brief_received", "Đã nhận một lệnh sản xuất", {"prompt": request.prompt})
    manager.start(project_id, initial_state)
    return public_project(project)


@app.get("/api/projects")
async def list_projects():
    return [public_project(item) for item in db.list_projects()]


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    artifacts = db.get_artifacts(project_id)
    for artifact in artifacts:
        artifact["url"] = artifact_url(artifact["path"])
    return {
        **public_project(project),
        "tasks": db.get_tasks(project_id),
        "events": db.get_events(project_id),
        "artifacts": artifacts,
        "agents": db.list_project_agents(project_id),
        "approvals": db.list_approvals(project_id),
        "interventions": db.list_interventions(project_id),
        "quality_tests": db.list_quality_tests(project_id),
    }


@app.get("/api/projects/{project_id}/agents")
async def list_project_agents(project_id: str):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    return db.list_project_agents(project_id)


@app.post("/api/projects/{project_id}/agents", status_code=201)
async def create_project_agent(project_id: str, request: CreateAgentRequest):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] != "paused":
        raise HTTPException(409, "Chỉ có thể thêm agent khi dự án đang tạm dừng")
    custom_agents = db.list_project_agents(project_id, custom_only=True)
    if len(custom_agents) >= 10:
        raise HTTPException(409, "Mỗi dự án được thêm tối đa 10 agent")
    model_config = {
        "model": request.model, "fallback_models": request.fallback_models,
        "image_model": request.image_model, "temperature": request.temperature,
    }
    validate_model_choices(model_config)
    agent = db.create_project_agent(
        project_id,
        request.name.strip(),
        request.role_key,
        request.instructions.strip(),
        request.color,
        request.model,
        list(dict.fromkeys(request.fallback_models)),
        request.temperature,
        request.image_model,
    )
    db.add_helper_task(project_id, agent)
    db.add_event(
        project_id,
        "pm",
        "agent_added",
        f"Đã thêm agent {agent['name']} — {agent['role']}",
        {"agent_id": agent["id"]},
    )
    return agent


@app.patch("/api/projects/{project_id}/agents/{agent_id}")
async def update_project_agent(project_id: str, agent_id: str, request: UpdateAgentRequest):
    agent = db.get_project_agent(project_id, agent_id)
    if not agent:
        raise HTTPException(404, "Không tìm thấy agent")
    changes = request.model_dump(exclude_unset=True)
    model_fields = {"model", "fallback_models", "image_model", "temperature"}
    if agent["is_core"] and any(key not in model_fields for key in changes):
        raise HTTPException(403, "Agent mặc định chỉ cho phép sửa cấu hình model")
    fallbacks = changes.get("fallback_models")
    if fallbacks is not None:
        changes["fallback_models"] = list(dict.fromkeys(
            model.strip() for model in fallbacks if model.strip()
        ))
    if changes.get("role_key"):
        changes["role"] = WORKER_ROLE_LABELS[changes["role_key"]]
    validate_model_choices(changes)
    if not db.update_project_agent(project_id, agent_id, **changes):
        raise HTTPException(404, "Không tìm thấy agent")
    updated = db.get_project_agent(project_id, agent_id)
    if changes.get("role_key") or ("name" in changes and not updated["is_core"]):
        db.remove_agent_tasks(project_id, agent_id)
        db.add_helper_task(project_id, updated)
    db.add_event(
        project_id,
        "pm",
        "agent_updated",
        f"Đã cập nhật agent {updated['name']}",
        {
            "agent_id": agent_id, "enabled": updated["enabled"],
            "model": updated.get("model"), "fallback_models": updated.get("fallback_models", []),
            "image_model": updated.get("image_model"),
        },
    )
    return updated


@app.delete("/api/projects/{project_id}/agents/{agent_id}")
async def delete_project_agent(project_id: str, agent_id: str):
    agent = db.get_project_agent(project_id, agent_id)
    if not agent:
        raise HTTPException(404, "Không tìm thấy agent")
    if agent["is_core"]:
        raise HTTPException(403, "Không thể xóa 6 agent mặc định")
    if not db.delete_project_agent(project_id, agent_id):
        raise HTTPException(404, "Không tìm thấy agent")
    db.add_event(
        project_id,
        "pm",
        "agent_removed",
        f"Đã xóa agent {agent['name']}",
        {"agent_id": agent_id},
    )
    return {"status": "deleted", "agent_id": agent_id}


@app.get("/api/projects/{project_id}/events")
async def get_events(project_id: str, after: int = Query(0, ge=0)):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    return db.get_events(project_id, after)


@app.get("/api/projects/{project_id}/events/{event_id}/content")
async def get_event_content(project_id: str, event_id: int):
    project = db.get_project(project_id)
    event = db.get_event(project_id, event_id)
    if not project or not event:
        raise HTTPException(404, "Không tìm thấy tin nhắn")
    approval = None
    approval_id = event["payload"].get("approval_id")
    if approval_id:
        approval = db.get_approval(project_id, int(approval_id))
    state = load_state(project)
    key = event_content_key(event["agent"])
    payload = event.get("payload", {})
    artifact_ids = [int(item) for item in payload.get("artifact_ids", [])]
    scoped = bool(artifact_ids or payload.get("unit_key") or payload.get("test_id"))
    content = approval["content"] if approval else (
        payload.get("content") or payload.get("result") or payload
        if scoped else state.get(key) if key else payload
    )
    artifacts = []
    for item in db.get_artifacts(project_id):
        if item["id"] in artifact_ids:
            item["url"] = artifact_url(item["path"])
            artifacts.append(item)
    return {
        "event": event, "content_key": None if scoped else key, "content": content or {},
        "artifacts": artifacts, "approval": approval,
        "editable": project["status"] == "paused" and key is not None and not scoped,
        "can_intervene": project["status"] == "paused",
    }


@app.put("/api/projects/{project_id}/events/{event_id}/content")
async def update_event_content(
    project_id: str, event_id: int, request: UpdateContentRequest,
):
    project = db.get_project(project_id)
    event = db.get_event(project_id, event_id)
    if not project or not event:
        raise HTTPException(404, "Không tìm thấy tin nhắn")
    if project["status"] != "paused":
        raise HTTPException(409, "Phải tạm dừng công việc trước khi chỉnh sửa nội dung")
    key = event_content_key(event["agent"])
    if key not in {"plan", "script", "character_bible", "page_prompts", "review"}:
        raise HTTPException(400, "Tin nhắn này không có nội dung có thể chỉnh sửa")
    if key == "page_prompts" and not isinstance(request.content, list):
        raise HTTPException(422, "Prompt ảnh phải là một danh sách")
    if key != "page_prompts" and not isinstance(request.content, dict):
        raise HTTPException(422, "Nội dung phải là một JSON object")
    state = load_state(project)
    before = state.get(key)
    state[key] = request.content
    db.update_project(
        project_id, state_json=json.dumps(state, ensure_ascii=False), error=None,
    )
    intervention_id = db.add_intervention(
        project_id, "edit_content", event_id=event_id, content_key=key,
        before=before, after=request.content,
    )
    db.add_event(
        project_id, "user", "content_edited",
        f"Bạn đã chỉnh sửa {key} trong khi dự án tạm dừng.",
        {"intervention_id": intervention_id, "source_event_id": event_id, "content_key": key},
    )
    return {"status": "saved", "content_key": key, "content": request.content}


@app.patch("/api/projects/{project_id}/settings")
async def update_project_settings(project_id: str, request: ProjectSettingsRequest):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    stages = list(dict.fromkeys(request.approval_stages))
    db.update_project(
        project_id, approval_enabled=request.approval_enabled, approval_stages=stages,
    )
    db.add_event(
        project_id, "user", "approval_settings_updated",
        "Đã bật duyệt nội dung" if request.approval_enabled else "Đã tắt duyệt nội dung",
        {"enabled": request.approval_enabled, "stages": stages},
    )
    return public_project(db.get_project(project_id))


@app.post("/api/projects/{project_id}/approvals/{approval_id}", status_code=202)
async def decide_approval(
    project_id: str, approval_id: int, request: ApprovalDecisionRequest,
):
    project = db.get_project(project_id)
    approval = db.get_approval(project_id, approval_id)
    if not project or not approval:
        raise HTTPException(404, "Không tìm thấy yêu cầu duyệt")
    if project["status"] != "awaiting_approval" or approval["status"] != "pending":
        raise HTTPException(409, "Yêu cầu duyệt này không còn ở trạng thái chờ")
    state = load_state(project)
    if request.decision == "approve":
        if not db.resolve_approval(project_id, approval_id, "approved"):
            raise HTTPException(409, "Nội dung đã được xử lý")
        db.add_event(
            project_id, "user", "content_approved",
            f"Bạn đã duyệt nội dung {approval['stage']}.",
            {"approval_id": approval_id},
        )
    else:
        if not request.feedback.strip():
            raise HTTPException(422, "Cần nhập yêu cầu chỉnh sửa")
        default_agent = {
            "script": "writer", "character_design": "designer",
            "illustration": "artist", "final": "editor",
        }[approval["stage"]]
        target = request.target_agent or default_agent
        if not db.resolve_approval(
            project_id, approval_id, "revision_requested", request.feedback.strip(), target,
        ):
            raise HTTPException(409, "Nội dung đã được xử lý")
        state.update({
            "stage": revision_stage(target), "feedback": request.feedback.strip(),
            "revision_target": target, "revision_count": state.get("revision_count", 0) + 1,
            "completed": False,
        })
        db.add_revision_task(
            project_id, target, f"Yêu cầu sửa của người dùng: {target}",
            request.feedback.strip(), 50 + state["revision_count"],
        )
        db.add_intervention(
            project_id, "approval_revision", event_id=approval.get("event_id"),
            target_agent=target, feedback=request.feedback.strip(),
        )
        db.add_event(
            project_id, "user", "revision_requested",
            f"Bạn yêu cầu {target} làm lại: {request.feedback.strip()}",
            {"approval_id": approval_id, "to": target},
        )
        db.update_project(
            project_id, stage=state["stage"],
            state_json=json.dumps(state, ensure_ascii=False), error=None,
        )
    manager.start(project_id, state)
    return {"status": "running", "decision": request.decision}


@app.post("/api/projects/{project_id}/interventions")
async def create_intervention(project_id: str, request: InterventionRequest):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] != "paused":
        raise HTTPException(409, "Phải tạm dừng công việc trước khi can thiệp")
    if request.event_id and not db.get_event(project_id, request.event_id):
        raise HTTPException(404, "Không tìm thấy tin nhắn nguồn")
    state = load_state(project)
    state.update({
        "stage": revision_stage(request.target_agent), "feedback": request.feedback.strip(),
        "revision_target": request.target_agent,
        "revision_count": state.get("revision_count", 0) + 1, "completed": False,
    })
    db.update_project(
        project_id, stage=state["stage"],
        state_json=json.dumps(state, ensure_ascii=False), error=None,
    )
    intervention_id = db.add_intervention(
        project_id, "request_revision", event_id=request.event_id,
        target_agent=request.target_agent, feedback=request.feedback.strip(),
    )
    db.add_revision_task(
        project_id, request.target_agent, f"Can thiệp: {request.target_agent}",
        request.feedback.strip(), 50 + state["revision_count"],
    )
    db.add_event(
        project_id, "user", "intervention_created",
        f"Đã giao {request.target_agent} xử lý khi tiếp tục dự án.",
        {"intervention_id": intervention_id, "to": request.target_agent},
    )
    return {"status": "queued_while_paused", "intervention_id": intervention_id}


@app.get("/api/projects/{project_id}/events/stream")
async def stream_events(project_id: str, after: int = Query(0, ge=0)):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")

    async def event_stream():
        cursor = after
        idle = 0
        while True:
            events = db.get_events(project_id, cursor)
            for item in events:
                cursor = item["id"]
                yield f"id: {cursor}\nevent: workflow\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            project = db.get_project(project_id)
            if project and project["status"] in {
                "completed", "failed", "needs_attention", "stopped", "paused", "awaiting_approval",
            } and not events:
                idle += 1
                if idle >= 2:
                    break
            else:
                idle = 0
            yield ": heartbeat\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/projects/{project_id}/retry", status_code=202)
async def retry_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] == "running":
        return {"status": "already_running"}
    if project["status"] == "awaiting_approval":
        raise HTTPException(409, "Hãy duyệt hoặc yêu cầu sửa nội dung đang chờ")
    state = load_state(project)
    state["completed"] = False
    if state.get("stage") == "needs_attention":
        state["stage"] = state.get("revision_target") or "review"
        state["revision_count"] = 0
    db.add_event(project_id, "system", "workflow_retried", "Đã khởi động lại từ stage gần nhất")
    manager.start(project_id, state)
    return {"status": "running"}


@app.post("/api/projects/{project_id}/pause", status_code=202)
async def pause_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] in {"paused", "pause_requested"}:
        return {"status": project["status"]}
    if project["status"] not in {"running", "queued"}:
        raise HTTPException(409, "Chỉ có thể tạm dừng dự án đang chạy")
    manager.pause(project_id)
    return {"status": db.get_project(project_id)["status"]}


@app.post("/api/projects/{project_id}/resume", status_code=202)
async def resume_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] != "paused":
        raise HTTPException(409, "Dự án không ở trạng thái tạm dừng")
    state = load_state(project)
    state["completed"] = False
    db.add_event(
        project_id, "user", "workflow_resumed",
        "Bạn đã tiếp tục dự án từ điểm lưu gần nhất.",
    )
    manager.start(project_id, state)
    return {"status": "running"}


@app.post("/api/projects/{project_id}/stop")
async def stop_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] not in {"running", "queued", "pause_requested"}:
        return {"status": project["status"]}

    stopped = await manager.stop(project_id)
    if not stopped:
        # Persist the user's intent after a process restart or a task completion race.
        db.update_project(
            project_id, status="stopped", pause_requested=False, error=None,
        )
        db.add_event(project_id, "system", "workflow_stopped", "Đã dừng dự án theo yêu cầu")
    return {"status": "stopped"}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    running = manager.running.get(project_id)
    if project["status"] in {"running", "queued", "pause_requested"} or (
        running and not running.done()
    ):
        raise HTTPException(409, "Không thể xóa dự án đang chạy")

    artifacts_root = settings.artifacts_dir.resolve()
    project_dir = (artifacts_root / project_id).resolve()
    try:
        project_dir.relative_to(artifacts_root)
    except ValueError as error:
        raise HTTPException(400, "Đường dẫn artifact không hợp lệ") from error
    if project_dir.exists():
        shutil.rmtree(project_dir)
    if not db.delete_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    return {"status": "deleted", "project_id": project_id}

