from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..schemas import ComicState
from ..services.layout import LayoutService
from ..services.router import RouterExhaustedError
from .base import BaseAgent


class EditorAgent(BaseAgent):
    agent_id = "editor"
    display_name = "Biên tập & dàn trang"

    SYSTEM = """Bạn là biên tập trưởng truyện tranh. Duyệt mạch truyện, mức an toàn theo tuổi,
độ nhất quán nhân vật/bối cảnh và việc prompt ảnh có trung thành kịch bản. Chỉ chấm REVISE khi có lỗi
NGHIÊM TRỌNG làm sai nội dung, không an toàn, thiếu trang/cảnh, hoặc đổi ngoại hình. Lỗi nhỏ phải ghi
vào minor_notes và vẫn PASS. Nếu REVISE, chỉ định đúng MỘT agent: writer (cốt truyện/lời thoại),
designer (anchor/ngoại hình/style), artist (prompt/ảnh không theo kịch bản). Không tự sửa kịch bản hay
vẽ lại ảnh. Nếu trên 25% lượt thoại dưới 6 từ, câu cụt hoặc không truyền đạt đủ ý thì coi là lỗi
nghiêm trọng của writer; vài câu cảm thán ngắn có ngữ cảnh vẫn được chấp nhận."""

    SCHEMA = """{
      "verdict": "PASS|REVISE",
      "summary": "kết luận ngắn",
      "serious_issues": [{"category": "...", "reason": "...", "evidence": "..."}],
      "minor_notes": ["..."],
      "revision_agent": "writer|designer|artist|none",
      "revision_instructions": "chỉ dẫn cụ thể, ràng buộc không đổi phần đã đạt",
      "scores": {"story": 0, "age_safety": 0, "consistency": 0, "script_fidelity": 0}
    }"""

    def __init__(self, *args, layout: LayoutService, settings: Settings, **kwargs):
        super().__init__(*args, **kwargs)
        self.layout = layout
        self.settings = settings

    async def run(self, state: ComicState) -> ComicState:
        if state.get("stage") == "layout":
            return self._layout(state)
        self.started(state, "review", 84)
        prompt = (
            f"Production brief:\n{state['plan']}\n\nKịch bản:\n{state['script']}\n\n"
            f"Character bible:\n{state['character_bible']}\n\nPage prompts:\n{state['page_prompts']}\n\n"
            f"Số ảnh trang thực tế: {len(state.get('page_images', []))}."
        )
        prompt += self.expert_context(state)
        contact_sheet = self.layout.make_contact_sheet(
            Path(state["cover_image"]), [Path(path) for path in state.get("page_images", [])],
            self.project_dir(state) / "review-contact-sheet.jpg",
        )
        self.db.add_artifact(
            state["project_id"], self.agent_id, "review_sheet", "Contact sheet kiểm duyệt", str(contact_sheet)
        )
        try:
            review, usage = await self.router.chat_json(
                system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
                temperature=0.1, on_attempt=self.model_attempt(state), image_paths=[contact_sheet],
                timeout_seconds=60,
            )
        except RouterExhaustedError as error:
            self.event(
                state, "automatic_recovery",
                "Model duyệt timeout; Biên tập chạy quality gate kỹ thuật trên kịch bản, anchor và ảnh",
                {"error": str(error)},
            )
            review = self._deterministic_review(state)
            usage = {"model": "deterministic-editor-recovery", "prompt_tokens": 0, "completion_tokens": 0}
        verdict = str(review.get("verdict", "PASS")).upper()
        serious = review.get("serious_issues", [])
        if verdict == "REVISE" and not serious:
            verdict = "PASS"
            review["verdict"] = "PASS"
            review.setdefault("minor_notes", []).append("Không có bằng chứng lỗi nghiêm trọng; cho đạt theo policy.")
        self.save_json(state, f"05-review-{state.get('revision_count', 0) + 1}.json", review, "review")
        if verdict == "REVISE":
            return self._revision(state, review, usage)
        self.db.update_project(state["project_id"], stage="layout", progress=90)
        self.event(state, "review_passed", "Biên tập kết luận ĐẠT; chuyển sang dàn trang", review)
        return {
            **state, "review": review, "stage": "layout",
            "model_usage": [*state.get("model_usage", []), usage],
        }

    def _revision(self, state: ComicState, review: dict, usage: dict) -> ComicState:
        count = state.get("revision_count", 0) + 1
        target = str(review.get("revision_agent", "artist"))
        if target not in {"writer", "designer", "artist"}:
            target = "artist"
        instructions = str(review.get("revision_instructions") or review.get("summary") or "Sửa lỗi nghiêm trọng")
        if count > self.settings.max_revisions:
            error = f"Đã chạm giới hạn {self.settings.max_revisions} vòng sửa. Lỗi cuối: {instructions}"
            self.db.update_project(state["project_id"], status="needs_attention", stage="needs_attention", error=error, progress=96)
            self.event(state, "revision_limit", error, review)
            return {
                **state, "review": review, "stage": "needs_attention", "completed": True,
                "error": error, "revision_count": count,
                "model_usage": [*state.get("model_usage", []), usage],
            }
        progress_by_target = {"writer": 18, "designer": 36, "artist": 52}
        stage_by_target = {"writer": "script", "designer": "character_design", "artist": "illustration"}
        self.db.update_project(state["project_id"], stage=stage_by_target[target], progress=progress_by_target[target])
        self.db.set_task_status(state["project_id"], target, "in_progress", instructions)
        self.db.add_revision_task(
            state["project_id"], target, f"Vòng sửa {count}: {target}", instructions, 10 + count,
        )
        self.event(
            state, "revision_assigned", f"Biên tập trả về {target}: {instructions}",
            {"to": target, "revision": count, "review": review},
        )
        return {
            **state, "review": review, "stage": stage_by_target[target], "revision_target": target,
            "revision_count": count, "feedback": instructions,
            "model_usage": [*state.get("model_usage", []), usage],
        }

    def _layout(self, state: ComicState) -> ComicState:
        self.started(state, "layout", 92)
        final_dir = self.project_dir(state) / "final"
        final_cover = self.layout.finalize_cover(
            Path(state["cover_image"]), state["title"], final_dir / "cover.png"
        )
        self.db.add_artifact(
            state["project_id"], self.agent_id, "cover_final", "Bìa hoàn thiện", str(final_cover)
        )
        final_pages: list[Path] = []
        script_pages = state["script"].get("pages", [])
        for index, (raw, page) in enumerate(zip(state["page_images"], script_pages), start=1):
            output = final_dir / f"page-{index:02d}.png"
            prompt_info = state.get("page_prompts", [])[index - 1] if index <= len(state.get("page_prompts", [])) else {}
            layout_page = {**page, "dialogue_zone": prompt_info.get("dialogue_zone", "top")}
            self.layout.add_dialogue(Path(raw), layout_page, output)
            final_pages.append(output)
            self.db.add_artifact(state["project_id"], self.agent_id, "page_final", f"Trang {index} — hoàn thiện", str(output))
        destination = final_dir / "comic.pdf"
        metadata = {
            "title": state["title"], "project_id": state["project_id"],
            "lesson": state["script"].get("lesson", ""), "review": state.get("review", {}),
            "model_usage": state.get("model_usage", []),
        }
        self.layout.make_pdf(final_cover, final_pages, destination, metadata)
        self.db.add_artifact(state["project_id"], self.agent_id, "final_pdf", f"{state['title']}.pdf", str(destination))
        self.db.set_task_status(state["project_id"], self.agent_id, "done")
        self.db.update_project(state["project_id"], stage="finalized", progress=98, final_pdf=str(destination))
        self.event(state, "artifact_ready", "PDF truyện tranh đã sẵn sàng", {"path": str(destination)})
        self.completed(state, "Đã gắn bóng thoại, hoàn thiện bìa và ghép PDF")
        return {**state, "final_pdf": str(destination), "stage": "finalized", "completed": True}

    @staticmethod
    def _deterministic_review(state: ComicState) -> dict:
        expected = int(state["plan"].get("page_count", 0))
        script_pages = state["script"].get("pages", [])
        prompts = state.get("page_prompts", [])
        images = state.get("page_images", [])
        bible = state.get("character_bible", {})
        all_dialogues = [
            dialogue for page in script_pages for dialogue in page.get("dialogues", [])
        ]
        short_dialogues = [
            dialogue for dialogue in all_dialogues
            if len(str(dialogue.get("text", "")).split()) < 6
        ]
        issues = []
        target = "none"
        if len(script_pages) != expected:
            target = "writer"
            issues.append({
                "category": "page_count", "reason": "Kịch bản không đủ số trang đã khóa",
                "evidence": f"expected={expected}, actual={len(script_pages)}",
            })
        elif all_dialogues and len(short_dialogues) / len(all_dialogues) > 0.25:
            target = "writer"
            issues.append({
                "category": "dialogue_quality",
                "reason": "Quá nhiều câu thoại ngắn, cộc lốc hoặc chưa đủ ý",
                "evidence": f"short={len(short_dialogues)}, total={len(all_dialogues)}",
            })
        elif not bible.get("style_lock") or any(
            not item.get("fixed_anchor") for item in bible.get("characters", [])
        ):
            target = "designer"
            issues.append({
                "category": "character_lock", "reason": "Thiếu style/character anchor bắt buộc",
                "evidence": "character_bible validation failed",
            })
        elif len(prompts) != expected or len(images) != expected or any(
            not Path(path).is_file() for path in images
        ):
            target = "artist"
            issues.append({
                "category": "artwork", "reason": "Thiếu page prompt hoặc file ảnh trang",
                "evidence": f"prompts={len(prompts)}, images={len(images)}, expected={expected}",
            })
        verdict = "REVISE" if issues else "PASS"
        return {
            "verdict": verdict,
            "summary": "Quality gate kỹ thuật phát hiện lỗi nghiêm trọng" if issues else "Đủ trang, ảnh và khóa nhất quán; đạt để dàn trang",
            "serious_issues": issues,
            "minor_notes": [
                "Model semantic review bị timeout; đã xác nhận cấu trúc, số trang, file ảnh và anchor bằng deterministic gate."
            ],
            "revision_agent": target,
            "revision_instructions": "Khôi phục thành phần bị thiếu, không thay đổi phần đã đạt." if issues else "",
            "scores": {
                "story": 8 if len(script_pages) == expected else 4,
                "age_safety": 8, "consistency": 9 if bible.get("style_lock") else 4,
                "script_fidelity": 9 if len(prompts) == expected else 4,
            },
        }

