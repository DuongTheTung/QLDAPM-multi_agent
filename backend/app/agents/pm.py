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
        self.step(state, "pm_scope", "PM đang phân tích yêu cầu và khóa phạm vi")
        models, temperature, _ = self.model_config(state, 0.25)
        plan, usage = await self.router.chat_json(
            system=self.SYSTEM,
            prompt=f"Lập production brief từ yêu cầu duy nhất này:\n{state['user_prompt']}",
            schema_hint=self.SCHEMA,
            temperature=temperature,
            on_attempt=self.model_attempt(state),
            models=models,
        )
        self.progress(state, 55)
        plan["page_count"] = max(4, min(24, int(plan.get("page_count", 8))))
        title = str(plan.get("title") or state.get("title") or "Truyện mới")[:120]
        custom_agents = self.db.list_project_agents(
            state["project_id"], custom_only=True, enabled_only=True
        )
        tasks = self._schedule(state["project_id"], plan["page_count"], custom_agents)
        self.db.replace_tasks(state["project_id"], tasks)
        self.progress(state, 78)
        self.step(state, "pm_schedule", "PM đang kiểm tra dependency và lịch sản xuất")
        self.step(state, "pm_handoff", "PM đã đồng bộ lịch, quan hệ phụ thuộc và bàn giao công việc")
        self.progress(state, 95)
        self.db.update_project(state["project_id"], title=title, stage="script", progress=10)
        self.save_json(state, "01-production-plan.json", plan, "plan")
        self.completed(state, f"PM đã khóa brief “{title}” và lập {len(tasks)} work item")
        self.event(state, "handoff", "PM bàn giao bản yêu cầu sản xuất cho Biên kịch", {"to": "writer"})
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
        tasks: list[dict[str, Any]] = []
        prefix = project_id[:6]

        def add_group(
            code: str, title: str, agent: str, start: int, end: int,
            dependency_codes: list[str], detail: str,
            subtasks: list[tuple[str, str, str]],
        ) -> None:
            parent_id = f"{prefix}-{code}"
            done = False
            tasks.append({
                "id": parent_id, "title": title, "agent": agent,
                "status": "done" if done else "todo",
                "start_at": (now + timedelta(minutes=start)).isoformat(),
                "due_at": (now + timedelta(minutes=end)).isoformat(),
                "depends_on": [f"{prefix}-{item}" for item in dependency_codes],
                "detail": detail, "order_index": len(tasks), "parent_id": None,
                "item_type": "task", "step_key": "",
            })
            duration = max(1, end - start)
            for index, (suffix, subtask_title, step_key) in enumerate(subtasks):
                sub_start = start + int(duration * index / len(subtasks))
                sub_end = start + int(duration * (index + 1) / len(subtasks))
                subtask_id = f"{parent_id}-{suffix}"
                previous = f"{parent_id}-{subtasks[index - 1][0]}" if index else None
                tasks.append({
                    "id": subtask_id, "title": subtask_title, "agent": agent,
                    "status": "done" if done else "todo",
                    "start_at": (now + timedelta(minutes=sub_start)).isoformat(),
                    "due_at": (now + timedelta(minutes=sub_end)).isoformat(),
                    "depends_on": [previous] if previous else [
                        f"{prefix}-{item}" for item in dependency_codes
                    ],
                    "detail": f"Đầu ra bắt buộc: {subtask_title.lower()}.",
                    "order_index": len(tasks), "parent_id": parent_id,
                    "item_type": "subtask", "step_key": step_key,
                })

        add_group(
            "PM", "Quản lý và đồng bộ kế hoạch sản xuất", "pm", 0, 15, [],
            "PM khóa phạm vi, quan hệ phụ thuộc, lịch và theo dõi toàn bộ công việc cùng việc nhỏ.",
            [
                ("01", "Phân tích yêu cầu và khóa phạm vi", "pm_scope"),
                ("02", "Lập dependency, lịch và tiêu chí nghiệm thu", "pm_schedule"),
                ("03", "Bàn giao danh sách việc cho từng agent", "pm_handoff"),
            ],
        )
        script_start = 15
        add_group(
            "SCRIPT", "Viết và khóa kịch bản phân trang", "writer",
            script_start, script_start + 30, ["PM"],
            "Kịch bản phải đủ mở–thắt–cao trào–kết–bài học và đúng số trang.",
            [
                ("01", "Dựng cấu trúc câu chuyện và bài học", "writer_structure"),
                ("02", f"Chia nội dung thành đúng {page_count} trang", "writer_pages"),
                ("03", "Viết và kiểm tra đoạn kể đầy đủ theo từng trang", "writer_story_text"),
            ],
        )
        add_group(
            "DESIGN", "Khóa thiết kế nhân vật và bối cảnh", "designer",
            script_start + 30, script_start + 70, ["SCRIPT"],
            "Không vẽ trang truyện; chỉ tạo bible, anchor cố định và ảnh tham chiếu.",
            [
                ("01", "Tạo hồ sơ nhân vật và khóa phong cách", "designer_bible"),
                ("02", "Khóa anchor nhân vật và bối cảnh", "designer_anchors"),
                ("03", "Tạo bộ ảnh tham chiếu nhân vật", "designer_references"),
            ],
        )
        art_end = script_start + 70 + page_count * 18
        add_group(
            "ART", f"Minh họa bìa và {page_count} trang truyện", "artist",
            script_start + 70, art_end, ["DESIGN"],
            "Giữ nguyên kịch bản/ngoại hình; dùng toàn khung tranh vì chữ được đặt ở cột riêng.",
            [
                ("01", "Ghép prompt ảnh từ kịch bản và anchor", "artist_prompts"),
                ("02", "Tạo ảnh bìa không có chữ", "artist_cover"),
                ("03", f"Tạo đủ {page_count} ảnh trang truyện", "artist_pages"),
            ],
        )
        add_group(
            "REVIEW", "Kiểm duyệt tổng thể trước dàn trang", "reviewer",
            art_end, art_end + 25, ["ART"],
            "Kiểm tra các đầu ra và trả lỗi nghiêm trọng về đúng agent.",
            [
                ("01", "Đối chiếu mạch truyện và an toàn độ tuổi", "reviewer_story"),
                ("02", "Đối chiếu nhân vật, ảnh và kịch bản", "reviewer_visual"),
                ("03", "Kết luận đạt hoặc trả đúng agent sửa", "reviewer_final"),
            ],
        )
        add_group(
            "EDITOR", "Dàn trang và xuất PDF", "editor",
            art_end + 25, art_end + 55, ["REVIEW"],
            "Ghép tranh và đoạn kể thành hai vùng riêng, hoàn thiện bìa và xuất PDF.",
            [
                ("01", "Ghép tranh bên trái và đoạn kể bên phải", "editor_layout"),
                ("02", "Kiểm tra từng trang sau dàn", "editor_pages"),
                ("03", "Hoàn thiện bìa và xuất PDF", "editor_pdf"),
            ],
        )
        role_parents = {
            "writer": f"{prefix}-SCRIPT", "designer": f"{prefix}-DESIGN",
            "artist": f"{prefix}-ART", "reviewer": f"{prefix}-REVIEW",
            "editor": f"{prefix}-EDITOR",
        }
        for agent in custom_agents:
            role_key = str(agent.get("role_key") or "")
            parent_id = role_parents.get(role_key)
            parent = next((item for item in tasks if item["id"] == parent_id), None)
            if not parent:
                continue
            tasks.append({
                "id": f"{parent_id}-HELP-{str(agent['id'])[-6:]}",
                "title": f"{agent['name']} hỗ trợ {agent['role']}", "agent": agent["id"],
                "status": "todo", "start_at": parent["start_at"], "due_at": parent["due_at"],
                "depends_on": [],
                "detail": f"PM chia phần việc trong lane {agent['role']} cho {agent['name']}.",
                "order_index": len(tasks), "parent_id": parent_id, "item_type": "subtask",
                "step_key": f"{role_key}_support_{str(agent['id'])[-6:]}",
            })
        return tasks

