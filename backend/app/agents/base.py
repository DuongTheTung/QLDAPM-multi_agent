from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import Database
from ..exceptions import AutomaticRevision
from ..schemas import ComicState
from ..services.router import NineRouterClient


class BaseAgent:
    agent_id = "agent"
    display_name = "Agent"

    def __init__(self, db: Database, router: NineRouterClient, artifacts_root: Path):
        self.db = db
        self.router = router
        self.artifacts_root = artifacts_root
        self.reviewer: Any | None = None

    def project_dir(self, state: ComicState) -> Path:
        path = self.artifacts_root / state["project_id"]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def event(self, state: ComicState, event_type: str, message: str, payload: dict | None = None) -> None:
        self.db.add_event(state["project_id"], self.agent_id, event_type, message, payload)

    def started(self, state: ComicState, stage: str, progress: int) -> None:
        project = self.db.get_project(state["project_id"])
        fields: dict[str, Any] = {"stage": stage, "progress": progress}
        if not project or not project.get("pause_requested"):
            fields["status"] = "running"
        self.db.update_project(state["project_id"], **fields)
        self.db.start_agent_work(state["project_id"], self.agent_id)
        self.event(state, "agent_started", f"{self.display_name} bắt đầu: {stage}")

    def completed(self, state: ComicState, message: str) -> None:
        self.db.complete_agent_work(state["project_id"], self.agent_id)
        self.event(state, "agent_completed", message)

    def step(self, state: ComicState, step_key: str, message: str) -> None:
        self.db.set_task_step(state["project_id"], self.agent_id, step_key)
        self.event(state, "subtask_started", message, {"step_key": step_key})

    def progress(
        self, state: ComicState, value: int, *, owner: str | None = None,
        reset: bool = False,
    ) -> None:
        self.db.set_agent_progress(
            state["project_id"], owner or self.agent_id, value, reset=reset,
        )

    def direct_approval_stage(self, state: ComicState) -> str | None:
        approval_stage = {
            "writer": "script",
            "designer": "character_design",
            "artist": "illustration",
            "editor": "final",
        }.get(self.agent_id)
        if not approval_stage:
            return None
        project = self.db.get_project(state["project_id"])
        if (
            project
            and project.get("approval_enabled")
            and approval_stage in project.get("approval_stages", [])
        ):
            return approval_stage
        return None

    def human_approved_stages(self, state: ComicState) -> set[str]:
        """Return stages whose latest human decision is approval."""
        latest: dict[str, str] = {}
        for approval in self.db.list_approvals(state["project_id"]):
            latest[str(approval["stage"])] = str(approval["status"])
        return {stage for stage, status in latest.items() if status == "approved"}

    async def quality_gate(
        self,
        state: ComicState,
        step_key: str,
        title: str,
        *,
        content: Any = None,
        image_path: Path | None = None,
        artifact_ids: list[int] | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        approval_stage = self.direct_approval_stage(state)
        if approval_stage:
            output_owner = owner or self.agent_id
            self.db.add_event(
                state["project_id"], output_owner, "waiting_for_user_approval",
                f"{title} sẽ được chuyển thẳng đến bạn duyệt, không qua Kiểm duyệt tự động trước.",
                {"approval_stage": approval_stage, "unit_key": step_key},
            )
            return {
                "verdict": "PASS",
                "summary": "Đầu ra được dành cho người dùng duyệt trực tiếp.",
                "serious_issues": [],
                "notes": ["Đã bỏ qua Kiểm duyệt tự động trước bước duyệt của người dùng."],
            }
        if step_key in state.get("review_bypass", []):
            bypass_owner = owner or self.agent_id
            self.db.finish_task_testing(
                state["project_id"], bypass_owner, step_key, True,
            )
            self.event(
                state, "quality_override",
                f"Cho phép tiếp tục {title} sau các vòng giao sửa tự động.",
                {"unit_key": step_key, "owner": bypass_owner},
            )
            return {
                "verdict": "PASS", "summary": "Đã ghi chú để tiếp tục sau giới hạn vòng sửa.",
                "serious_issues": [], "notes": ["Quality gate được nới sau nhiều vòng sửa."],
            }
        if self.reviewer is None:
            return {"verdict": "PASS", "summary": "Reviewer chưa được gắn."}
        return await self.reviewer.inspect_unit(
            state, owner=owner or self.agent_id, unit_key=step_key, title=title,
            content=content, image_path=image_path, artifact_ids=artifact_ids,
        )

    def revise_if_needed(
        self, state: ComicState, result: dict[str, Any], unit_key: str,
    ) -> None:
        if str(result.get("verdict", "PASS")).upper() != "REVISE":
            return
        feedback = str(result.get("summary") or "Sửa lỗi nghiêm trọng được Kiểm duyệt phát hiện.")
        self.event(
            state, "automatic_revision_requested",
            f"Kiểm duyệt tự giao lại {self.display_name}: {feedback}",
            {"to": self.agent_id, "unit_key": unit_key, "result": result},
        )
        raise AutomaticRevision(self.agent_id, unit_key, feedback)

    def model_attempt(self, state: ComicState):
        def callback(model: str, attempt: int, fallback: bool) -> None:
            self.event(
                state,
                "model_fallback" if fallback else "model_call",
                f"{'Chuyển sang' if fallback else 'Đang gọi'} {model}",
                {"model": model, "attempt": attempt, "fallback": fallback},
            )
        return callback

    def model_config(
        self, state: ComicState, default_temperature: float,
    ) -> tuple[list[str] | None, float, str | None]:
        agent = next(
            (
                item for item in self.db.list_project_agents(state["project_id"])
                if item.get("key") == self.agent_id
            ),
            None,
        )
        if not agent:
            return None, default_temperature, None
        primary = str(agent.get("model") or "").strip()
        fallbacks = [str(model).strip() for model in agent.get("fallback_models", []) if str(model).strip()]
        configured = [primary, *fallbacks] if primary or fallbacks else []
        models = list(dict.fromkeys([*configured, *self.router.settings.models])) if configured else None
        temperature = agent.get("temperature")
        return models, float(temperature) if temperature is not None else default_temperature, (
            str(agent.get("image_model") or "").strip() or None
        )

    def role_workers(self, state: ComicState) -> list[dict[str, Any]]:
        return self.db.role_workers(state["project_id"], self.agent_id)

    def worker_model_config(
        self, state: ComicState, worker: dict[str, Any], default_temperature: float,
    ) -> tuple[list[str] | None, float, str | None]:
        primary = str(worker.get("model") or "").strip()
        fallbacks = [
            str(model).strip() for model in worker.get("fallback_models", [])
            if str(model).strip()
        ]
        configured = [primary, *fallbacks] if primary or fallbacks else []
        models = list(dict.fromkeys([*configured, *self.router.settings.models])) if configured else None
        temperature = worker.get("temperature")
        return models, float(temperature) if temperature is not None else default_temperature, (
            str(worker.get("image_model") or "").strip() or None
        )

    def worker_event(
        self, state: ComicState, worker: dict[str, Any], event_type: str,
        message: str, payload: dict[str, Any] | None = None,
    ) -> None:
        self.db.add_event(
            state["project_id"], str(worker["runtime_id"]), event_type, message, payload,
        )

    def worker_step_key(self, worker: dict[str, Any], default: str) -> str:
        if worker.get("is_core"):
            return default
        return f"{self.agent_id}_support_{str(worker['id'])[-6:]}"

    def worker_attempt(self, state: ComicState, worker: dict[str, Any]):
        def callback(model: str, attempt: int, fallback: bool) -> None:
            self.worker_event(
                state, worker, "model_fallback" if fallback else "model_call",
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

