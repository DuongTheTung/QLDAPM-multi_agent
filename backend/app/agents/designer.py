from __future__ import annotations

import asyncio

from ..schemas import ComicState
from ..services.images import ImageService
from .base import BaseAgent


class DesignerAgent(BaseAgent):
    agent_id = "designer"
    display_name = "Thiết kế nhân vật"

    SYSTEM = """Bạn là character designer kiêm art director. Hãy tạo hồ sơ nhân vật và khóa một
phong cách tranh nhất quán. Với mỗi nhân vật và bối cảnh, tạo một đoạn ANCHOR mô tả cố định, độc lập,
cụ thể; các anchor này sẽ được chèn NGUYÊN VĂN vào mọi prompt ảnh. Không vẽ trang truyện, không đổi
kịch bản, không thêm nhân vật quan trọng. Mô tả ngoại hình phải an toàn và phù hợp lứa tuổi."""

    SCHEMA = """{
      "style_lock": "đoạn phong cách cố định gồm medium, line, palette, lighting, age safety",
      "negative_lock": "những điều luôn tránh",
      "characters": [{
        "name": "đúng tên trong kịch bản", "role": "...", "profile": "...",
        "fixed_anchor": "CHARACTER ANCHOR — mô tả nguyên văn chi tiết khuôn mặt, tóc/lông, tỷ lệ, trang phục, màu",
        "reference_prompt": "model sheet front/side/expressions, nền đơn sắc"
      }],
      "settings": [{
        "name": "...", "fixed_anchor": "SETTING ANCHOR — kiến trúc, vật thể, palette, ánh sáng cố định"
      }]
    }"""

    def __init__(self, *args, image_service: ImageService, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = image_service

    async def run(self, state: ComicState) -> ComicState:
        self.started(state, "character_design", 36)
        self.step(state, "designer_bible", "Thiết kế đang tạo hồ sơ nhân vật và khóa phong cách")
        feedback = state.get("feedback", "")
        prompt = f"Production brief:\n{state['plan']}\n\nKịch bản đã khóa:\n{state['script']}"
        prompt += self.expert_context(state)
        if feedback:
            prompt += f"\n\nYêu cầu sửa của biên tập:\n{feedback}"
        models, temperature, _ = self.model_config(state, 0.45)
        bible, usage = await self.router.chat_json(
            system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
            temperature=temperature, on_attempt=self.model_attempt(state), models=models,
        )
        self.progress(state, 26)
        self.step(state, "designer_anchors", "Thiết kế đang kiểm tra anchor nhân vật và bối cảnh")
        self.save_json(state, "03-character-bible.json", bible, "character_bible")
        bible_test = await self.quality_gate(
            state, "designer_bible", "Hồ sơ nhân vật và khóa phong cách", content=bible,
        )
        self.revise_if_needed(state, bible_test, "designer_bible")
        anchor_test = await self.quality_gate(
            state, "designer_anchors", "Anchor nhân vật và bối cảnh", content=bible,
        )
        self.revise_if_needed(state, anchor_test, "designer_anchors")
        self.progress(state, 38)
        refs_dir = self.project_dir(state) / "references"
        workers = self.role_workers(state)
        for worker in workers[1:]:
            self.progress(state, 3, owner=str(worker["runtime_id"]), reset=True)
        characters = bible.get("characters", [])
        worker_totals = {str(worker["runtime_id"]): 0 for worker in workers}
        worker_done = {str(worker["runtime_id"]): 0 for worker in workers}
        for index, _character in enumerate(characters, start=1):
            worker_id = str(workers[(index - 1) % len(workers)]["runtime_id"])
            worker_totals[worker_id] += 1
        self.step(
            state, "designer_references",
            f"Đang chia ảnh tham chiếu cho {len(workers)} agent Thiết kế",
        )
        semaphore = asyncio.Semaphore(min(4, len(workers)))
        worker_locks = {
            str(worker["runtime_id"]): asyncio.Semaphore(1) for worker in workers
        }

        async def render_reference(index: int, character: dict, worker: dict) -> None:
            worker_id = str(worker["runtime_id"])
            step_key = self.worker_step_key(worker, "designer_references")
            self.db.set_task_status(state["project_id"], worker_id, "in_progress")
            base = 38 if worker.get("is_core") else 5
            total = max(1, worker_totals[worker_id])
            self.progress(
                state, round(base + (92 - base) * (worker_done[worker_id] + 0.15) / total),
                owner=worker_id,
            )
            safe_name = f"character-{index:02d}.png"
            image_prompt = (
                f"{bible.get('style_lock', '')}\n{character.get('fixed_anchor', '')}\n"
                f"{character.get('reference_prompt', '')}\n"
                "Professional character model sheet, front view, side view, five facial expressions, white background."
            )
            _, _, image_model = self.worker_model_config(state, worker, 0.45)
            async with semaphore, worker_locks[worker_id]:
                path = await self.images.generate(
                    image_prompt, refs_dir / safe_name, landscape=True,
                    on_warning=lambda message: self.worker_event(
                        state, worker, "warning", message,
                    ),
                    model=image_model,
                )
            self.progress(
                state, round(base + (92 - base) * (worker_done[worker_id] + 0.7) / total),
                owner=worker_id,
            )
            artifact_id = self.db.add_artifact(
                state["project_id"], worker_id, "reference_image",
                character.get("name", safe_name), str(path),
            )
            self.worker_event(
                state, worker, "unit_completed",
                f"{worker['name']} hoàn thành ảnh tham chiếu {character.get('name', index)}",
                {"artifact_ids": [artifact_id], "content": character, "unit_key": step_key},
            )
            result = await self.quality_gate(
                state, step_key,
                f"Ảnh tham chiếu {character.get('name', index)}", content=character,
                image_path=path, artifact_ids=[artifact_id], owner=worker_id,
            )
            self.revise_if_needed(state, result, step_key)
            worker_done[worker_id] += 1
            self.progress(
                state, round(base + (92 - base) * worker_done[worker_id] / total),
                owner=worker_id,
            )
        await asyncio.gather(*(
            render_reference(index, character, workers[(index - 1) % len(workers)])
            for index, character in enumerate(characters, start=1)
        ))
        self.progress(state, 97)
        for worker in workers[1:]:
            self.db.complete_agent_work(state["project_id"], str(worker["runtime_id"]))
            self.worker_event(
                state, worker, "agent_completed",
                f"{worker['name']} đã hoàn thành phần thiết kế được PM phân công",
            )
        self.db.update_project(state["project_id"], stage="illustration", progress=48)
        self.completed(
            state,
            f"Đã khóa phong cách và {len(bible.get('characters', []))} mô tả nhân vật cố định",
        )
        if self.direct_approval_stage(state):
            self.event(
                state, "waiting_for_user_approval",
                "Hồ sơ nhân vật và ảnh tham chiếu đã hoàn thành, được chuyển thẳng đến bạn duyệt.",
                {"to": "user", "approval_stage": "character_design"},
            )
        else:
            self.event(
                state, "handoff",
                "Thiết kế đã được kiểm tra; bàn giao hồ sơ và ảnh tham chiếu cho Họa sĩ",
                {"to": "artist"},
            )
        return {
            **state, "character_bible": bible, "stage": "illustration", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

