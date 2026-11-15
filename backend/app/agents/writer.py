from __future__ import annotations

from ..schemas import ComicState
from .base import BaseAgent


class WriterAgent(BaseAgent):
    agent_id = "writer"
    display_name = "Biên kịch"

    SYSTEM = """Bạn là biên kịch truyện tranh thiếu nhi chuyên nghiệp. Kịch bản bắt buộc có mở,
thắt, cao trào, kết và bài học. Chia chính xác theo từng trang. Lời thoại phải tự nhiên, phù hợp độ
tuổi, mỗi câu ghi rõ người nói và truyền đạt một ý đầy đủ. Mỗi lượt thoại nên dài 7-22 từ, có chủ-vị
hoặc ngữ cảnh rõ ràng; tránh câu cụt lủn như “Ừ”, “Đi thôi”, “Không đâu” nếu đứng một mình. Mỗi trang
nên có 1-3 lượt thoại để câu chuyện đủ cảm xúc nhưng không che tranh. Mỗi trang phải mô tả hành động
có thể vẽ được. Không đưa hướng dẫn vẽ chi tiết, không làm character design. Tôn trọng tuyệt đối
production brief."""

    SCHEMA = """{
      "logline": "...", "theme": "...", "lesson": "...",
      "structure": {"opening": "...", "rising_action": "...", "climax": "...", "ending": "..."},
      "characters": [{"name": "...", "role": "...", "age_or_type": "...", "traits": ["..."]}],
      "pages": [{
        "page_number": 1, "beat": "opening|rising_action|climax|ending",
        "setting": "...", "action": "...", "emotion": "...",
        "dialogues": [{"speaker": "Tên nhân vật", "text": "câu đầy đủ ý, tự nhiên, 7-22 từ"}],
        "caption": "tùy chọn hoặc rỗng"
      }]
    }"""

    async def run(self, state: ComicState) -> ComicState:
        self.started(state, "script", 18)
        self.step(state, "writer_structure", "Biên kịch đang dựng cấu trúc câu chuyện")
        feedback = state.get("feedback", "")
        prompt = (
            f"Yêu cầu gốc:\n{state['user_prompt']}\n\nProduction brief:\n{state['plan']}\n"
            f"\nHãy viết đúng {state['plan']['page_count']} trang. Mỗi lượt thoại phải đủ ý, tự nhiên, "
            "ưu tiên 7-22 từ; không dùng câu cộc lốc hoặc chỉ một vài từ nếu không có ngữ cảnh."
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
        pages_test = await self.quality_gate(
            state, "writer_pages", "Kịch bản phân trang", content={"pages": pages},
        )
        if pages_test.get("verdict") == "REVISE":
            raise ValueError(f"Phân trang chưa đạt kiểm duyệt: {pages_test.get('summary', '')}")
        self.step(state, "writer_dialogue", "Biên kịch đang hoàn thiện và kiểm tra lời thoại")
        self.save_json(state, "02-script.json", script, "script")
        dialogue_test = await self.quality_gate(
            state, "writer_dialogue", "Lời thoại hoàn chỉnh", content={"pages": pages},
        )
        if dialogue_test.get("verdict") == "REVISE":
            raise ValueError(f"Lời thoại chưa đạt kiểm duyệt: {dialogue_test.get('summary', '')}")
        self.db.update_project(state["project_id"], stage="character_design", progress=30)
        self.completed(state, f"Đã hoàn thành kịch bản {expected} trang")
        self.event(state, "handoff", "Kịch bản đã qua Testing; bàn giao Thiết kế nhân vật", {"to": "designer"})
        return {
            **state, "script": script, "stage": "character_design", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

