from __future__ import annotations

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
        models, temperature, image_model = self.model_config(state, 0.45)
        bible, usage = await self.router.chat_json(
            system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
            temperature=temperature, on_attempt=self.model_attempt(state), models=models,
        )
        self.step(state, "designer_anchors", "Thiết kế đang kiểm tra anchor nhân vật và bối cảnh")
        self.save_json(state, "03-character-bible.json", bible, "character_bible")
        bible_test = await self.quality_gate(
            state, "designer_bible", "Hồ sơ nhân vật và khóa phong cách", content=bible,
        )
        if bible_test.get("verdict") == "REVISE":
            raise ValueError(f"Character bible chưa đạt kiểm duyệt: {bible_test.get('summary', '')}")
        anchor_test = await self.quality_gate(
            state, "designer_anchors", "Anchor nhân vật và bối cảnh", content=bible,
        )
        if anchor_test.get("verdict") == "REVISE":
            raise ValueError(f"Anchor chưa đạt kiểm duyệt: {anchor_test.get('summary', '')}")
        refs_dir = self.project_dir(state) / "references"

        def warning(message: str) -> None:
            self.event(state, "warning", message)

        self.step(state, "designer_references", "Thiết kế đang tạo bộ ảnh tham chiếu")
        for index, character in enumerate(bible.get("characters", []), start=1):
            safe_name = f"character-{index:02d}.png"
            image_prompt = (
                f"{bible.get('style_lock', '')}\n{character.get('fixed_anchor', '')}\n"
                f"{character.get('reference_prompt', '')}\n"
                "Professional character model sheet, front view, side view, five facial expressions, white background."
            )
            path = await self.images.generate(
                image_prompt, refs_dir / safe_name, landscape=True,
                on_warning=warning, model=image_model,
            )
            artifact_id = self.db.add_artifact(
                state["project_id"], self.agent_id, "reference_image",
                character.get("name", safe_name), str(path),
            )
            self.event(
                state, "unit_completed",
                f"Thiết kế hoàn thành ảnh tham chiếu {character.get('name', index)}; chuyển sang Testing",
                {"artifact_ids": [artifact_id], "content": character, "unit_key": f"reference_{index}"},
            )
            result = await self.quality_gate(
                state, "designer_references",
                f"Ảnh tham chiếu {character.get('name', index)}", content=character,
                image_path=path, artifact_ids=[artifact_id],
            )
            if result.get("verdict") == "REVISE":
                raise ValueError(f"Ảnh tham chiếu chưa đạt kiểm duyệt: {result.get('summary', '')}")
        self.db.update_project(state["project_id"], stage="illustration", progress=48)
        self.completed(state, f"Đã khóa style và {len(bible.get('characters', []))} character anchor")
        self.event(state, "handoff", "Thiết kế đã qua Testing; bàn giao bible và ảnh tham chiếu cho Họa sĩ", {"to": "artist"})
        return {
            **state, "character_bible": bible, "stage": "illustration", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

