from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..schemas import ComicState
from .base import BaseAgent


class PMAgent(BaseAgent):
    agent_id = "pm"
    display_name = "PM"

    SYSTEM = """Bạn là PM của xưởng sản xuất truyện tranh tự động. Bạn biến một brief thô thành
kế hoạch khả thi, ưu tiên an toàn theo độ tuổi, phạm vi rõ ràng và lịch tuần tự. Không sáng tác toàn
bộ kịch bản. Không yêu cầu người dùng trả lời thêm; hãy tự chọn mặc định hợp lý từ brief."""

    SCHEMA = """{
      "title": "tên truyện ngắn",
      "audience_age": "ví dụ 7-10",
      "language": "vi",
      "page_count": 6,
      "genre": "phiêu lưu",
      "tone": "ấm áp",
      "safety_notes": ["..."],
      "acceptance_criteria": ["..."],
      "visual_format": "portrait comic page"
    }"""

    async def run(self, state: ComicState) -> ComicState:
        if state.get("completed") or state.get("stage") in {"finalized", "needs_attention"}:
            return self._close(state)

        self.started(state, "planning", 5)
        plan, usage = await self.router.chat_json(
            system=self.SYSTEM,
            prompt=f"Lập production brief từ yêu cầu duy nhất này:\n{state['user_prompt']}",
            schema_hint=self.SCHEMA,
            temperature=0.25,
            on_attempt=self.model_attempt(state),
        )
        plan["page_count"] = max(4, min(24, int(plan.get("page_count", 8))))
        title = str(plan.get("title") or state.get("title") or "Truyện mới")[:120]
        custom_agents = self.db.list_project_agents(
            state["project_id"], custom_only=True, enabled_only=True
        )
        tasks = self._schedule(state["project_id"], plan["page_count"], custom_agents)
        self.db.replace_tasks(state["project_id"], tasks)
        self.db.update_project(state["project_id"], title=title, stage="script", progress=10)
        self.save_json(state, "01-production-plan.json", plan, "plan")
        self.completed(state, f"PM đã khóa brief “{title}” và lập {len(tasks)} work item")
        self.event(state, "handoff", "PM bàn giao production brief cho Biên kịch", {"to": "writer"})
        return {
            **state,
            "title": title,
            "plan": plan,
            "stage": "script",
            "revision_count": 0,
            "model_usage": [*state.get("model_usage", []), usage],
        }

    def _close(self, state: ComicState) -> ComicState:
        needs_attention = state.get("stage") == "needs_attention"
        status = "needs_attention" if needs_attention else "completed"
        progress = 96 if needs_attention else 100
        self.db.update_project(
            state["project_id"], status=status, stage=state.get("stage", "finalized"),
            progress=progress, final_pdf=state.get("final_pdf"), error=state.get("error"),
        )
        self.db.set_task_status(state["project_id"], "pm", "done")
        self.event(
            state, "project_needs_attention" if needs_attention else "project_completed",
            "Dự án cần kiểm tra vì đã chạm giới hạn vòng sửa" if needs_attention else "PM đã nghiệm thu và đóng dự án",
        )
        return state

    @staticmethod
    def _schedule(
        project_id: str, page_count: int, custom_agents: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        custom_agents = custom_agents or []
        consultation_minutes = len(custom_agents) * 8
        consultation_ids = [f"CONSULT-{index + 1}" for index in range(len(custom_agents))]
        specs = [
            ("PM-PLAN", "Lập production brief & lịch", "pm", 0, 15, []),
        ]
        specs.extend(
            (
                consultation_ids[index], f"Tư vấn: {agent['role']}", agent["id"],
                15 + index * 8, 23 + index * 8, ["PM-PLAN"],
            )
            for index, agent in enumerate(custom_agents)
        )
        script_start = 15 + consultation_minutes
        specs.extend([
            ("SCRIPT", "Kịch bản phân trang", "writer", script_start, script_start + 30, consultation_ids or ["PM-PLAN"]),
            ("DESIGN", "Character bible & ảnh tham chiếu", "designer", script_start + 30, script_start + 70, ["SCRIPT"]),
            ("ART", f"Bìa & {page_count} trang tranh", "artist", script_start + 70, script_start + 70 + page_count * 18, ["DESIGN"]),
            ("EDITOR", "Quality gate, bóng thoại & PDF", "editor", script_start + 70 + page_count * 18, script_start + 105 + page_count * 18, ["ART"]),
        ])
        tasks = []
        for index, (task_id, title, agent, start, end, deps) in enumerate(specs):
            tasks.append({
                "id": f"{project_id[:6]}-{task_id}", "title": title, "agent": agent,
                "status": "done" if agent == "pm" else "todo",
                "start_at": (now + timedelta(minutes=start)).isoformat(),
                "due_at": (now + timedelta(minutes=end)).isoformat(),
                "depends_on": [f"{project_id[:6]}-{dep}" for dep in deps],
                "detail": "", "order_index": index,
            })
        return tasks

