from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import Database
from ..schemas import ComicState
from ..services.router import NineRouterClient


class BaseAgent:
    agent_id = "agent"
    display_name = "Agent"

    def __init__(self, db: Database, router: NineRouterClient, artifacts_root: Path):
        self.db = db
        self.router = router
        self.artifacts_root = artifacts_root

    def project_dir(self, state: ComicState) -> Path:
        path = self.artifacts_root / state["project_id"]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def event(self, state: ComicState, event_type: str, message: str, payload: dict | None = None) -> None:
        self.db.add_event(state["project_id"], self.agent_id, event_type, message, payload)

    def started(self, state: ComicState, stage: str, progress: int) -> None:
        self.db.update_project(state["project_id"], status="running", stage=stage, progress=progress)
        self.db.set_task_status(state["project_id"], self.agent_id, "in_progress")
        self.event(state, "agent_started", f"{self.display_name} bắt đầu: {stage}")

    def completed(self, state: ComicState, message: str) -> None:
        self.db.set_task_status(state["project_id"], self.agent_id, "done")
        self.event(state, "agent_completed", message)

    def model_attempt(self, state: ComicState):
        def callback(model: str, attempt: int, fallback: bool) -> None:
            self.event(
                state,
                "model_fallback" if fallback else "model_call",
                f"{'Chuyển sang' if fallback else 'Đang gọi'} {model}",
                {"model": model, "attempt": attempt, "fallback": fallback},
            )
        return callback

    def expert_context(self, state: ComicState) -> str:
        outputs = state.get("custom_agent_outputs", [])
        configured = self.db.list_project_agents(
            state["project_id"], custom_only=True, enabled_only=True
        )
        if not outputs and not configured:
            return ""
        context = {
            "configured_specialists": [
                {
                    "name": agent["name"],
                    "role": agent["role"],
                    "instructions": agent["instructions"],
                }
                for agent in configured
            ],
            "consultation_outputs": outputs,
        }
        return "\n\nAgent chuyên gia bổ sung và tư vấn của họ:\n" + json.dumps(
            context, ensure_ascii=False, indent=2
        )

    def save_json(self, state: ComicState, name: str, data: Any, kind: str) -> Path:
        path = self.project_dir(state) / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.db.add_artifact(state["project_id"], self.agent_id, kind, name, str(path))
        return path

