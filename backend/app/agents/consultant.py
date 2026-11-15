from __future__ import annotations

import json

from ..db import Database
from ..schemas import ComicState
from ..services.router import NineRouterClient


class ConsultantCoordinator:
    """Runs optional per-project specialists before the core production agents."""

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
        if not agents:
            return {**state, "custom_agent_outputs": []}

        outputs: list[dict] = []
        usages = list(state.get("model_usage", []))
        for agent in agents:
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
                        f"Bạn là {agent['name']}, chuyên gia {agent['role']} trong một xưởng truyện tranh. "
                        f"Hướng dẫn làm việc riêng của bạn:\n{agent['instructions']}\n"
                        "Chỉ tư vấn trong đúng chuyên môn, không thay đổi nhiệm vụ của 6 agent lõi."
                    ),
                    prompt=(
                        f"Yêu cầu người dùng:\n{state['user_prompt']}\n\n"
                        f"Kế hoạch PM:\n{json.dumps(state.get('plan', {}), ensure_ascii=False)}\n\n"
                        "Hãy đưa ra khuyến nghị ngắn, cụ thể để các agent lõi áp dụng."
                    ),
                    schema_hint=self.SCHEMA,
                    temperature=float(temperature) if temperature is not None else 0.35,
                    on_attempt=attempt,
                    models=models,
                )
                outputs.append({
                    "agent_id": agent_id,
                    "name": agent["name"],
                    "role": agent["role"],
                    "advice": advice,
                })
                usages.append(usage)
                self.db.set_task_status(state["project_id"], agent_id, "done")
                self.db.add_event(
                    state["project_id"], agent_id, "agent_completed",
                    f"{agent['name']} đã bàn giao tư vấn cho các agent lõi",
                    advice,
                )
            except Exception as error:  # noqa: BLE001 - optional agents cannot stop production
                self.db.set_task_status(
                    state["project_id"], agent_id, "done", f"Bỏ qua do lỗi: {error}"
                )
                self.db.add_event(
                    state["project_id"], agent_id, "automatic_recovery",
                    f"Bỏ qua tư vấn của {agent['name']} để workflow lõi tiếp tục",
                    {"error": str(error)},
                )

        return {**state, "custom_agent_outputs": outputs, "model_usage": usages}
