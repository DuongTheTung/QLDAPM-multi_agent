from __future__ import annotations

from ..schemas import ComicState
from .base import BaseAgent


class WriterAgent(BaseAgent):
    agent_id = "writer"
    display_name = "Biên kịch"

    SYSTEM = """Bạn là biên kịch truyện tranh thiếu nhi chuyên nghiệp. Kịch bản bắt buộc có mở,
thắt, cao trào, kết và bài học. Chia chính xác theo từng trang. Mỗi trang phải có story_text là một
đoạn văn kể chuyện hoàn chỉnh khoảng 60-110 từ, phù hợp độ tuổi, nối mạch tự nhiên với trang trước và
đủ rõ khi đọc cạnh một tranh minh họa. Có thể đưa lời nhân vật vào đoạn kể bằng dấu ngoặc kép, nhưng
không viết theo dạng bóng thoại rời rạc hoặc câu cụt lủn. Mỗi trang phải mô tả hành động có thể vẽ
được. Không đưa hướng dẫn vẽ chi tiết, không làm character design. Tôn trọng production brief."""

    SCHEMA = """{
      "logline": "...", "theme": "...", "lesson": "...",
      "structure": {"opening": "...", "rising_action": "...", "climax": "...", "ending": "..."},
      "characters": [{"name": "...", "role": "...", "age_or_type": "...", "traits": ["..."]}],
      "pages": [{
        "page_number": 1, "beat": "opening|rising_action|climax|ending",
        "setting": "...", "action": "...", "emotion": "...",
        "characters_present": ["Tên nhân vật xuất hiện trong tranh"],
        "story_text": "đoạn kể hoàn chỉnh 60-110 từ; lời nói nếu có được lồng tự nhiên trong đoạn",
        "dialogues": [{"speaker": "Tên nhân vật", "text": "câu được trích trong story_text nếu có"}]
      }]
    }"""

    async def run(self, state: ComicState) -> ComicState:
        self.started(state, "script", 18)
        self.step(state, "writer_structure", "Biên kịch đang dựng cấu trúc câu chuyện")
        feedback = state.get("feedback", "")
        prompt = (
            f"Yêu cầu gốc:\n{state['user_prompt']}\n\nProduction brief:\n{state['plan']}\n"
            f"\nHãy viết đúng {state['plan']['page_count']} trang. Mỗi trang phải có story_text "
            "khoảng 60-110 từ, kể đủ diễn biến và cảm xúc; chữ sẽ nằm ở cột riêng bên cạnh tranh."
        )
        prompt += self.expert_context(state)
        if feedback:
            prompt += f"\n\nĐây là vòng sửa. Chỉ sửa các lỗi biên tập đã chỉ ra, giữ phần tốt:\n{feedback}"
        models, temperature, _ = self.model_config(state, 0.65)
        script, usage = await self.router.chat_json(
            system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
            temperature=temperature, on_attempt=self.model_attempt(state), models=models,
        )
        structure_test = await self.quality_gate(
            state, "writer_structure", "Cấu trúc câu chuyện",
            content={"structure": script.get("structure"), "lesson": script.get("lesson")},
        )
        if structure_test.get("verdict") == "REVISE":
            raise ValueError(f"Cấu trúc chưa đạt kiểm duyệt: {structure_test.get('summary', '')}")
        pages = script.get("pages", [])
        self.step(state, "writer_pages", "Biên kịch đang kiểm tra phân trang")
        expected = state["plan"]["page_count"]
        if len(pages) != expected:
            raise ValueError(f"Biên kịch trả {len(pages)} trang, yêu cầu {expected}")
        for index, page in enumerate(pages, start=1):
            page["page_number"] = index
            page.setdefault("dialogues", [])
            story_text = str(page.get("story_text") or "").strip()
            if len(story_text.split()) < 35:
                raise ValueError(f"Đoạn kể trang {index} quá ngắn hoặc chưa có story_text")
        pages_test = await self.quality_gate(
            state, "writer_pages", "Kịch bản phân trang", content={"pages": pages},
        )
        if pages_test.get("verdict") == "REVISE":
            raise ValueError(f"Phân trang chưa đạt kiểm duyệt: {pages_test.get('summary', '')}")
        self.step(state, "writer_story_text", "Biên kịch đang hoàn thiện đoạn kể cho từng trang")
        self.save_json(state, "02-script.json", script, "script")
        story_test = await self.quality_gate(
            state, "writer_story_text", "Đoạn kể theo từng trang", content={"pages": pages},
        )
        if story_test.get("verdict") == "REVISE":
            raise ValueError(f"Đoạn kể chưa đạt kiểm duyệt: {story_test.get('summary', '')}")
        self.db.update_project(state["project_id"], stage="character_design", progress=30)
        self.completed(state, f"Đã hoàn thành kịch bản {expected} trang")
        self.event(state, "handoff", "Kịch bản đã qua Testing; bàn giao Thiết kế nhân vật", {"to": "designer"})
        return {
            **state, "script": script, "stage": "character_design", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

