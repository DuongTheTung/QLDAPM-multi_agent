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

from .config import get_settings
from .manager import WorkflowManager
from .runtime import db
from .schemas import CreateAgentRequest, CreateProjectRequest, UpdateAgentRequest
from .workflow import ComicWorkflow

settings = get_settings()
workflow = ComicWorkflow(db, settings)
manager = WorkflowManager(db, workflow)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
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


@app.get("/api/health")
async def health():
    return {
        "status": "ok", "router": settings.nine_router_base_url,
        "models": settings.models, "image_model": settings.nine_router_image_model,
        "api_key_configured": bool(settings.nine_router_api_key),
    }


@app.post("/api/projects", status_code=202)
async def create_project(request: CreateProjectRequest):
    project_id = uuid.uuid4().hex
    title = request.title or "Đang phân tích brief…"
    project = db.create_project(project_id, title, request.prompt.strip())
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
    }


@app.get("/api/projects/{project_id}/agents")
async def list_project_agents(project_id: str):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    return db.list_project_agents(project_id)


@app.post("/api/projects/{project_id}/agents", status_code=201)
async def create_project_agent(project_id: str, request: CreateAgentRequest):
    if not db.get_project(project_id):
        raise HTTPException(404, "Không tìm thấy dự án")
    custom_agents = db.list_project_agents(project_id, custom_only=True)
    if len(custom_agents) >= 10:
        raise HTTPException(409, "Mỗi dự án được thêm tối đa 10 agent")
    agent = db.create_project_agent(
        project_id,
        request.name.strip(),
        request.role.strip(),
        request.instructions.strip(),
        request.color,
    )
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
    if agent["is_core"]:
        raise HTTPException(403, "Không thể sửa 5 agent mặc định")
    if not db.update_project_agent(project_id, agent_id, **request.model_dump(exclude_none=True)):
        raise HTTPException(404, "Không tìm thấy agent")
    updated = db.get_project_agent(project_id, agent_id)
    db.add_event(
        project_id,
        "pm",
        "agent_updated",
        f"Đã cập nhật agent {updated['name']}",
        {"agent_id": agent_id, "enabled": updated["enabled"]},
    )
    return updated


@app.delete("/api/projects/{project_id}/agents/{agent_id}")
async def delete_project_agent(project_id: str, agent_id: str):
    agent = db.get_project_agent(project_id, agent_id)
    if not agent:
        raise HTTPException(404, "Không tìm thấy agent")
    if agent["is_core"]:
        raise HTTPException(403, "Không thể xóa 5 agent mặc định")
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
            if project and project["status"] in {"completed", "failed", "needs_attention", "stopped"} and not events:
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
    state = json.loads(project.get("state_json") or "{}")
    if not state:
        state = {
            "project_id": project_id, "user_prompt": project["prompt"], "title": project["title"],
            "stage": project["stage"], "revision_count": 0, "model_usage": [],
        }
    state["completed"] = False
    if state.get("stage") == "needs_attention":
        state["stage"] = state.get("revision_target") or "review"
        state["revision_count"] = 0
    db.add_event(project_id, "system", "workflow_retried", "Đã khởi động lại từ stage gần nhất")
    manager.start(project_id, state)
    return {"status": "running"}


@app.post("/api/projects/{project_id}/stop")
async def stop_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if project["status"] not in {"running", "queued"}:
        return {"status": project["status"]}

    stopped = await manager.stop(project_id)
    if not stopped:
        # Persist the user's intent after a process restart or a task completion race.
        db.update_project(project_id, status="stopped", error=None)
        db.add_event(project_id, "system", "workflow_stopped", "Đã dừng dự án theo yêu cầu")
    return {"status": "stopped"}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    running = manager.running.get(project_id)
    if project["status"] in {"running", "queued"} or (running and not running.done()):
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

