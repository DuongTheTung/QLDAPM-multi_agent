from __future__ import annotations

from ..schemas import ComicState
from ..services.images import ImageService
from ..services.router import RouterExhaustedError
from .base import BaseAgent


class ArtistAgent(BaseAgent):
    agent_id = "artist"
    display_name = "Họa sĩ"

    SYSTEM = """Bạn là họa sĩ truyện tranh production. Nhiệm vụ duy nhất là ghép prompt cho bìa và
từng trang từ kịch bản đã khóa cùng các anchor cố định. Không được đổi hành động, lời thoại, bối cảnh
hay ngoại hình. Prompt trang phải yêu cầu bố cục rõ và chừa vùng sáng/trống phía trên cho bóng thoại;
không render chữ, ký tự, watermark hoặc speech bubble trong ảnh. Sao chép nguyên văn style_lock và
mọi fixed_anchor liên quan vào trường prompt."""

    SCHEMA = """{
      "cover": {"prompt": "prompt đầy đủ có các anchor nguyên văn", "title_area": "top"},
      "pages": [{
        "page_number": 1,
        "prompt": "prompt đầy đủ, không chữ, có style + character + setting anchors nguyên văn",
        "dialogue_zone": "top-left|top|top-right",
        "continuity_note": "điểm cần giữ nhất quán"
      }]
    }"""

    def __init__(self, *args, image_service: ImageService, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = image_service

    async def run(self, state: ComicState) -> ComicState:
        self.started(state, "illustration", 52)
        feedback = state.get("feedback", "")
        prompt = (
            f"Kịch bản KHÔNG ĐƯỢC SỬA:\n{state['script']}\n\n"
            f"Character bible và anchors PHẢI CHÉP NGUYÊN VĂN:\n{state['character_bible']}"
        )
        prompt += self.expert_context(state)
        if feedback:
            prompt += f"\n\nSửa prompt/ảnh theo yêu cầu biên tập, không đổi kịch bản:\n{feedback}"
        try:
            prompt_pack, usage = await self.router.chat_json(
                system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
                temperature=0.35, on_attempt=self.model_attempt(state), timeout_seconds=60,
            )
        except RouterExhaustedError as error:
            # Artwork prompts are a deterministic composition task. If the text model is
            # temporarily unreachable, keep production moving without changing the script.
            self.event(
                state, "automatic_recovery",
                "Text model timeout; Họa sĩ ghép prompt trực tiếp từ kịch bản và các anchor đã khóa",
                {"error": str(error)},
            )
            prompt_pack = self._deterministic_prompt_pack(state)
            usage = {"model": "deterministic-artist-recovery", "prompt_tokens": 0, "completion_tokens": 0}
        expected = state["plan"]["page_count"]
        page_prompts = prompt_pack.get("pages", [])
        if len(page_prompts) != expected:
            raise ValueError(f"Họa sĩ tạo {len(page_prompts)} page prompt, yêu cầu {expected}")
        self._enforce_anchors(prompt_pack, state["character_bible"])
        self.save_json(state, "04-image-prompts.json", prompt_pack, "image_prompts")
        art_dir = self.project_dir(state) / "raw-art"

        def warning(message: str) -> None:
            self.event(state, "warning", message)

        cover = await self.images.generate(prompt_pack["cover"]["prompt"], art_dir / "cover.png", on_warning=warning)
        self.db.add_artifact(state["project_id"], self.agent_id, "cover_raw", "Bìa thô", str(cover))
        images: list[str] = []
        for index, item in enumerate(page_prompts, start=1):
            self.event(state, "page_rendering", f"Đang dựng trang {index}/{expected}", {"page": index})
            path = await self.images.generate(item["prompt"], art_dir / f"page-{index:02d}.png", on_warning=warning)
            images.append(str(path))
            self.db.add_artifact(state["project_id"], self.agent_id, "page_raw", f"Trang {index} — tranh thô", str(path))
            progress = 52 + int(28 * index / expected)
            self.db.update_project(state["project_id"], progress=progress)
        self.db.update_project(state["project_id"], stage="review", progress=82)
        self.completed(state, f"Đã dựng bìa và {expected} trang tranh")
        self.event(state, "handoff", "Họa sĩ bàn giao ảnh thô cho Biên tập", {"to": "editor"})
        return {
            **state, "page_prompts": page_prompts, "page_images": images,
            "cover_image": str(cover), "stage": "review", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

    @staticmethod
    def _enforce_anchors(pack: dict, bible: dict) -> None:
        anchors = [bible.get("style_lock", "")]
        anchors.extend(item.get("fixed_anchor", "") for item in bible.get("characters", []))
        anchors.extend(item.get("fixed_anchor", "") for item in bible.get("settings", []))
        fixed = "\n".join(anchor for anchor in anchors if anchor)
        negative = bible.get("negative_lock", "")
        suffix = f"\n{fixed}\nNEGATIVE LOCK: {negative}\nNo text, no letters, no watermark, no speech bubbles. Leave clean negative space at the top for dialogue."
        pack.setdefault("cover", {})["prompt"] = pack.get("cover", {}).get("prompt", "") + suffix
        for item in pack.get("pages", []):
            item["prompt"] = item.get("prompt", "") + suffix

    @staticmethod
    def _deterministic_prompt_pack(state: ComicState) -> dict:
        script = state["script"]
        pages = []
        for page in script.get("pages", []):
            dialogues = page.get("dialogues", [])
            speakers = ", ".join(
                dict.fromkeys(str(item.get("speaker", "")) for item in dialogues if item.get("speaker"))
            )
            visual = (
                f"COMIC PAGE {page.get('page_number')}. Setting: {page.get('setting', '')}. "
                f"Action exactly as scripted: {page.get('action', '')}. "
                f"Emotional tone: {page.get('emotion', '')}. Visible characters: {speakers or 'as scripted'}. "
                "Portrait comic composition, expressive cinematic storytelling, no written dialogue."
            )
            pages.append({
                "page_number": page.get("page_number"), "prompt": visual,
                "dialogue_zone": "top", "continuity_note": "Preserve every locked anchor verbatim.",
            })
        cover_prompt = (
            f"BOOK COVER for {state.get('title', '')}. Story premise: {script.get('logline', '')}. "
            f"Theme: {script.get('theme', '')}. Dynamic child-friendly portrait cover, central heroes, "
            "clear silhouette, generous clean title area at the top, no rendered text."
        )
        return {"cover": {"prompt": cover_prompt, "title_area": "top"}, "pages": pages}

