from __future__ import annotations

import asyncio
import json
import traceback
from typing import Any

from .db import Database
from .schemas import ComicState
from .workflow import ComicWorkflow


class WorkflowManager:
    def __init__(self, db: Database, workflow: ComicWorkflow):
        self.db = db
        self.workflow = workflow
        self.running: dict[str, asyncio.Task] = {}

    def start(self, project_id: str, state: ComicState) -> None:
        current = self.running.get(project_id)
        if current and not current.done():
            return
        self.running[project_id] = asyncio.create_task(self._run(project_id, state))

    async def stop(self, project_id: str) -> bool:
        task = self.running.get(project_id)
        if not task or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self.running.pop(project_id, None)
        self.db.update_project(
            project_id, status="stopped", pause_requested=False, error=None,
        )
        self.db.add_event(
            project_id,
            "system",
            "workflow_stopped",
            "Đã dừng dự án theo yêu cầu",
        )
        return True

    def pause(self, project_id: str) -> bool:
        project = self.db.get_project(project_id)
        if not project or project["status"] not in {"running", "queued", "pause_requested"}:
            return False
        self.db.update_project(
            project_id, status="pause_requested", pause_requested=True, error=None,
        )
        self.db.add_event(
            project_id, "system", "pause_requested",
            "Đã yêu cầu tạm dừng; agent sẽ dừng sau bước đang xử lý.",
        )
        task = self.running.get(project_id)
        if not task or task.done():
            self.db.update_project(
                project_id, status="paused", pause_requested=False, error=None,
            )
        return True

    async def _run(self, project_id: str, state: ComicState) -> None:
        try:
            self.db.update_project(
                project_id, status="running", pause_requested=False, error=None,
            )
            await self.workflow.run(state)
        except Exception as error:  # noqa: BLE001 - workflow boundary must persist every provider failure
            trace = traceback.format_exc(limit=8)
            self.db.update_project(project_id, status="failed", error=str(error))
            self.db.add_event(
                project_id, "system", "workflow_failed", f"Workflow dừng: {error}", {"trace": trace}
            )
        finally:
            self.running.pop(project_id, None)

    def resume_pending(self) -> None:
        for project in self.db.list_projects():
            if project["status"] == "pause_requested":
                self.db.update_project(
                    project["id"], status="paused", pause_requested=False,
                )
                continue
            if project["status"] not in {"queued", "running"}:
                continue
            raw = project.get("state_json") or "{}"
            state: dict[str, Any] = json.loads(raw)
            if not state:
                state = {
                    "project_id": project["id"], "user_prompt": project["prompt"],
                    "title": project["title"], "stage": project["stage"],
                    "revision_count": 0, "model_usage": [],
                }
            self.start(project["id"], state)  # reruns at the last safe stage

