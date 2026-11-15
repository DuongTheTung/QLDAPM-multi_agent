from __future__ import annotations

import asyncio

from ..schemas import ComicState
from ..services.images import ImageService
from ..services.router import RouterExhaustedError
from .base import BaseAgent


class ArtistAgent(BaseAgent):
    agent_id = "artist"
    display_name = "Họa sĩ"

    SYSTEM = """Bạn là họa sĩ truyện tranh production. Nhiệm vụ duy nhất là ghép prompt cho bìa và
từng trang từ kịch bản đã khóa cùng các anchor cố định. Không được đổi hành động, nội dung kể, bối
cảnh hay ngoại hình. Tranh phải tập trung hoàn toàn vào hình ảnh và bố cục nhân vật; không cần chừa
vùng đặt chữ vì văn bản nằm ở một cột riêng ngoài tranh. Không render chữ, ký tự, watermark hoặc
speech bubble trong ảnh. Sao chép nguyên văn style_lock và mọi fixed_anchor liên quan vào prompt."""

    SCHEMA = """{
      "cover": {"prompt": "prompt đầy đủ có các anchor nguyên văn", "title_area": "top"},
      "pages": [{
        "page_number": 1,
        "prompt": "prompt đầy đủ, không chữ, có style + character + setting anchors nguyên văn",
        "composition_note": "bố cục nhân vật và trọng tâm hình ảnh",
        "continuity_note": "điểm cần giữ nhất quán"
      }]
    }"""

    def __init__(self, *args, image_service: ImageService, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = image_service

    async def run(self, state: ComicState) -> ComicState:
        self.started(state, "illustration", 52)
        self.step(state, "artist_prompts", "Họa sĩ đang ghép prompt từ kịch bản và anchor")
        feedback = state.get("feedback", "")
        prompt = (
            f"Kịch bản KHÔNG ĐƯỢC SỬA:\n{state['script']}\n\n"
            f"Character bible và anchors PHẢI CHÉP NGUYÊN VĂN:\n{state['character_bible']}"
        )
        prompt += self.expert_context(state)
        if feedback:
            prompt += f"\n\nSửa prompt/ảnh theo yêu cầu biên tập, không đổi kịch bản:\n{feedback}"
        models, temperature, _ = self.model_config(state, 0.35)
        try:
            prompt_pack, usage = await self.router.chat_json(
                system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
                temperature=temperature, on_attempt=self.model_attempt(state), timeout_seconds=60,
                models=models,
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
        prompt_test = await self.quality_gate(
            state, "artist_prompts", "Bộ prompt minh họa", content=prompt_pack,
        )
        self.revise_if_needed(state, prompt_test, "artist_prompts")
        art_dir = self.project_dir(state) / "raw-art"
        workers = self.role_workers(state)
        lead = workers[0]
        _, _, lead_image_model = self.worker_model_config(state, lead, 0.35)

        def warning(worker: dict, message: str) -> None:
            self.worker_event(state, worker, "warning", message)

        self.step(state, "artist_cover", "Họa sĩ đang tạo ảnh bìa")
        cover = await self.images.generate(
            prompt_pack["cover"]["prompt"], art_dir / "cover.png",
            on_warning=lambda message: warning(lead, message), model=lead_image_model,
        )
        cover_id = self.db.add_artifact(
            state["project_id"], lead["runtime_id"], "cover_raw", "Bìa thô", str(cover),
        )
        self.worker_event(
            state, lead, "unit_completed",
            f"{lead['name']} hoàn thành ảnh bìa; chuyển sang Testing",
            {"unit_key": "artist_cover", "artifact_ids": [cover_id], "content": prompt_pack["cover"]},
        )
        cover_test = await self.quality_gate(
            state, "artist_cover", "Ảnh bìa", content=prompt_pack["cover"],
            image_path=cover, artifact_ids=[cover_id],
        )
        self.revise_if_needed(state, cover_test, "artist_cover")
        self.step(state, "artist_pages", f"Đang chia {expected} trang cho {len(workers)} Họa sĩ")
        semaphore = asyncio.Semaphore(min(4, len(workers)))
        worker_locks = {
            str(worker["runtime_id"]): asyncio.Semaphore(1) for worker in workers
        }

        async def render_page(index: int, item: dict, worker: dict) -> tuple[int, str]:
            worker_id = str(worker["runtime_id"])
            step_key = self.worker_step_key(worker, "artist_pages")
            self.db.set_task_status(state["project_id"], worker_id, "in_progress")
            self.worker_event(
                state, worker, "page_rendering",
                f"{worker['name']} đang dựng trang {index}/{expected}", {"page": index},
            )
            _, _, worker_image_model = self.worker_model_config(state, worker, 0.35)
            async with semaphore, worker_locks[worker_id]:
                path = await self.images.generate(
                    item["prompt"], art_dir / f"page-{index:02d}.png",
                    on_warning=lambda message: warning(worker, message), model=worker_image_model,
                )
            artifact_id = self.db.add_artifact(
                state["project_id"], worker_id, "page_raw",
                f"Trang {index} — tranh thô", str(path),
            )
            self.worker_event(
                state, worker, "unit_completed",
                f"{worker['name']} hoàn thành ảnh trang {index}; chuyển ngay sang Testing",
                {
                    "unit_key": step_key, "page": index,
                    "artifact_ids": [artifact_id], "content": item,
                },
            )
            page_test = await self.quality_gate(
                state, step_key, f"Ảnh trang {index}", content=item,
                image_path=path, artifact_ids=[artifact_id], owner=worker_id,
            )
            self.revise_if_needed(state, page_test, step_key)
            return index, str(path)

        results = await asyncio.gather(*(
            render_page(index, item, workers[(index - 1) % len(workers)])
            for index, item in enumerate(page_prompts, start=1)
        ))
        images = [path for _, path in sorted(results)]
        for worker in workers[1:]:
            self.db.complete_agent_work(state["project_id"], str(worker["runtime_id"]))
            self.worker_event(
                state, worker, "agent_completed",
                f"{worker['name']} đã hoàn thành phần minh họa được PM phân công",
            )
        self.db.update_project(state["project_id"], progress=80)
        self.db.update_project(state["project_id"], stage="testing", progress=82)
        self.completed(state, f"Đã dựng bìa và {expected} trang tranh")
        self.event(state, "handoff", "Họa sĩ bàn giao ảnh đã kiểm từng trang cho Kiểm duyệt", {"to": "reviewer"})
        return {
            **state, "page_prompts": page_prompts, "page_images": images,
            "cover_image": str(cover), "stage": "testing", "feedback": "",
            "model_usage": [*state.get("model_usage", []), usage],
        }

    @staticmethod
    def _enforce_anchors(pack: dict, bible: dict) -> None:
        anchors = [bible.get("style_lock", "")]
        anchors.extend(item.get("fixed_anchor", "") for item in bible.get("characters", []))
        anchors.extend(item.get("fixed_anchor", "") for item in bible.get("settings", []))
        fixed = "\n".join(anchor for anchor in anchors if anchor)
        negative = bible.get("negative_lock", "")
        suffix = f"\n{fixed}\nNEGATIVE LOCK: {negative}\nNo text, no letters, no watermark, no speech bubbles. Use the full frame for visual storytelling; no text-safe area is required."
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
                "composition_note": "Use the full frame for the scripted action.",
                "continuity_note": "Preserve every locked anchor verbatim.",
            })
        cover_prompt = (
            f"BOOK COVER for {state.get('title', '')}. Story premise: {script.get('logline', '')}. "
            f"Theme: {script.get('theme', '')}. Dynamic child-friendly portrait cover, central heroes, "
            "clear silhouette, generous clean title area at the top, no rendered text."
        )
        return {"cover": {"prompt": cover_prompt, "title_area": "top"}, "pages": pages}

