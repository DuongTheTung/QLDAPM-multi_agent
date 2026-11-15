from __future__ import annotations

import asyncio
import json

from ..db import Database
from ..schemas import ComicState
from ..services.router import NineRouterClient


class ConsultantCoordinator:
    """Runs optional writer workers in parallel before the lead writer consolidates."""

    SCHEMA = """{
      "recommendations": ["khuyến nghị cụ thể, có thể thực hiện"],
      "risks": ["rủi ro cần tránh"],
      "handoff_note": "ghi chú ngắn gửi các agent lõi"
    }"""

    def __init__(self, db: Database, router: NineRouterClient, **_: object):
        self.db = db
        self.router = router

    async def run(self, state: ComicState) -> ComicState:
        agents = self.db.list_project_agents(
            state["project_id"], custom_only=True, enabled_only=True
        )
        agents = [agent for agent in agents if agent.get("role_key") == "writer"]
        if not agents:
            return {**state, "custom_agent_outputs": []}

        async def run_worker(agent: dict) -> tuple[dict | None, dict | None]:
            agent_id = agent["id"]
            self.db.set_task_status(state["project_id"], agent_id, "in_progress")
            self.db.add_event(
                state["project_id"], agent_id, "agent_started",
                f"{agent['name']} bắt đầu tư vấn với vai trò {agent['role']}",
            )

            def attempt(
                model: str,
                attempt_number: int,
                fallback: bool,
                current_agent_id: str = agent_id,
            ) -> None:
                self.db.add_event(
                    state["project_id"], current_agent_id,
                    "model_fallback" if fallback else "model_call",
                    f"{'Chuyển sang' if fallback else 'Đang gọi'} {model}",
                    {"model": model, "attempt": attempt_number, "fallback": fallback},
                )

            try:
                primary = str(agent.get("model") or "").strip()
                fallback_models = [
                    str(model).strip() for model in agent.get("fallback_models", [])
                    if str(model).strip()
                ]
                configured = [primary, *fallback_models] if primary or fallback_models else []
                models = list(dict.fromkeys([
                    *configured, *self.router.settings.models,
                ])) if configured else None
                temperature = agent.get("temperature")
                advice, usage = await self.router.chat_json(
                    system=(
                        f"Bạn là {agent['name']}, Biên kịch hỗ trợ trong một xưởng truyện tranh. "
                        f"Hướng dẫn làm việc riêng của bạn:\n{agent['instructions']}\n"
                        "Hãy đề xuất chất liệu để Biên kịch chính tổng hợp; không tự khóa bản cuối."
                    ),
                    prompt=(
                        f"Yêu cầu người dùng:\n{state['user_prompt']}\n\n"
                        f"Kế hoạch PM:\n{json.dumps(state.get('plan', {}), ensure_ascii=False)}\n\n"
                        "Hãy đề xuất cấu trúc, cảnh và rủi ro để Biên kịch chính áp dụng."
                    ),
                    schema_hint=self.SCHEMA,
                    temperature=float(temperature) if temperature is not None else 0.35,
                    on_attempt=attempt,
                    models=models,
                )
                output = {
                    "agent_id": agent_id,
                    "name": agent["name"],
                    "role": agent["role"],
                    "advice": advice,
                }
                self.db.set_task_status(state["project_id"], agent_id, "done")
                self.db.add_event(
                    state["project_id"], agent_id, "agent_completed",
                    f"{agent['name']} đã bàn giao bản hỗ trợ cho Biên kịch chính",
                    advice,
                )
                return output, usage
            except Exception as error:  # noqa: BLE001 - optional agents cannot stop production
                self.db.set_task_status(
                    state["project_id"], agent_id, "done", f"Bỏ qua do lỗi: {error}"
                )
                self.db.add_event(
                    state["project_id"], agent_id, "automatic_recovery",
                    f"Bỏ qua tư vấn của {agent['name']} để workflow lõi tiếp tục",
                    {"error": str(error)},
                )
                return None, None

        results = await asyncio.gather(*(run_worker(agent) for agent in agents))
        outputs = [output for output, _ in results if output is not None]
        usages = [*state.get("model_usage", []), *[usage for _, usage in results if usage is not None]]
        return {**state, "custom_agent_outputs": outputs, "model_usage": usages}
