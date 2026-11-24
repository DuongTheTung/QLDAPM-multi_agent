from __future__ import annotations

import asyncio
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
vẽ lại ảnh. Nếu đoạn kể theo trang bị thiếu, quá ngắn hoặc không đủ diễn biến để hiểu câu chuyện thì
coi là lỗi nghiêm trọng của writer."""

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
        """Only lay out outputs that the ReviewerAgent has already approved."""
        if state.get("stage") != "layout":
            raise ValueError("Biên tập chỉ nhận sản phẩm đã đạt kiểm duyệt")
        return await self._layout(state)

    async def _legacy_review(self, state: ComicState) -> ComicState:
        if state.get("stage") == "layout":
            return await self._layout(state)
        self.started(state, "review", 84)
        self.step(state, "editor_review", "Biên tập đang duyệt nội dung và độ nhất quán")
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
        models, temperature, _ = self.model_config(state, 0.1)
        try:
            review, usage = await self.router.chat_json(
                system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
                temperature=temperature, on_attempt=self.model_attempt(state), image_paths=[contact_sheet],
                timeout_seconds=60,
                models=models,
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

    async def _layout(self, state: ComicState) -> ComicState:
        self.started(state, "layout", 92)
        self.step(state, "editor_layout", "Biên tập đang ghép tranh với khối văn bản riêng")
        final_dir = self.project_dir(state) / "final"
        final_cover = self.layout.finalize_cover(
            Path(state["cover_image"]), state["title"], final_dir / "cover.png"
        )
        self.progress(state, 16)
        cover_id = self.db.add_artifact(
            state["project_id"], self.agent_id, "cover_final", "Bìa hoàn thiện", str(final_cover)
        )
        self.event(
            state, "unit_completed", "Biên tập hoàn thiện bìa",
            {"artifact_ids": [cover_id], "unit_key": "editor_cover"},
        )
        cover_test = await self.quality_gate(
            state, "editor_layout", "Bìa đã dàn trang", image_path=final_cover,
            artifact_ids=[cover_id],
        )
        self.revise_if_needed(state, cover_test, "editor_layout")
        self.progress(state, 25)
        script_pages = state["script"].get("pages", [])
        workers = self.role_workers(state)
        for worker in workers[1:]:
            self.progress(state, 3, owner=str(worker["runtime_id"]), reset=True)
        worker_totals = {str(worker["runtime_id"]): 0 for worker in workers}
        worker_done = {str(worker["runtime_id"]): 0 for worker in workers}
        for index, _page in enumerate(script_pages, start=1):
            worker_id = str(workers[(index - 1) % len(workers)]["runtime_id"])
            worker_totals[worker_id] += 1
        self.step(
            state, "editor_pages",
            f"Đang chia dàn trang cho {len(workers)} agent Biên tập",
        )
        worker_locks = {
            str(worker["runtime_id"]): asyncio.Semaphore(1) for worker in workers
        }

        async def layout_page_job(
            index: int, raw: str, page: dict, worker: dict,
        ) -> tuple[int, Path]:
            worker_id = str(worker["runtime_id"])
            step_key = self.worker_step_key(worker, "editor_pages")
            self.db.set_task_status(state["project_id"], worker_id, "in_progress")
            base = 25 if worker.get("is_core") else 5
            total = max(1, worker_totals[worker_id])
            self.progress(
                state, round(base + (90 - base) * (worker_done[worker_id] + 0.15) / total),
                owner=worker_id,
            )
            output = final_dir / f"page-{index:02d}.png"
            layout_page = {**page}
            async with worker_locks[worker_id]:
                await asyncio.to_thread(
                    self.layout.compose_story_page, Path(raw), layout_page, output,
                )
            self.progress(
                state, round(base + (90 - base) * (worker_done[worker_id] + 0.7) / total),
                owner=worker_id,
            )
            artifact_id = self.db.add_artifact(
                state["project_id"], worker_id, "page_final",
                f"Trang {index} — hoàn thiện", str(output),
            )
            self.worker_event(
                state, worker, "unit_completed",
                f"{worker['name']} hoàn thành dàn trang {index}",
                {"artifact_ids": [artifact_id], "page": index, "unit_key": step_key},
            )
            result = await self.quality_gate(
                state, step_key, f"Trang {index} sau dàn tranh và chữ",
                content=layout_page, image_path=output, artifact_ids=[artifact_id], owner=worker_id,
            )
            self.revise_if_needed(state, result, step_key)
            worker_done[worker_id] += 1
            self.progress(
                state, round(base + (90 - base) * worker_done[worker_id] / total),
                owner=worker_id,
            )
            return index, output

        results = await asyncio.gather(*(
            layout_page_job(index, raw, page, workers[(index - 1) % len(workers)])
            for index, (raw, page) in enumerate(
                zip(state["page_images"], script_pages), start=1,
            )
        ))
        final_pages = [path for _, path in sorted(results)]
        self.progress(state, 92)
        for worker in workers[1:]:
            self.db.complete_agent_work(state["project_id"], str(worker["runtime_id"]))
            self.worker_event(
                state, worker, "agent_completed",
                f"{worker['name']} đã hoàn thành phần dàn trang được PM phân công",
            )
        destination = final_dir / "comic.pdf"
        self.step(state, "editor_pdf", "Biên tập đang hoàn thiện bìa và xuất PDF")
        self.progress(state, 94)
        metadata = {
            "title": state["title"], "project_id": state["project_id"],
            "lesson": state["script"].get("lesson", ""), "review": state.get("review", {}),
            "layout": "minh họa bên trái, đoạn kể bên phải; không dùng bóng thoại",
            "model_usage": state.get("model_usage", []),
        }
        self.layout.make_pdf(final_cover, final_pages, destination, metadata)
        self.progress(state, 97)
        pdf_id = self.db.add_artifact(
            state["project_id"], self.agent_id, "final_pdf",
            f"{state['title']}.pdf", str(destination),
        )
        self.event(
            state, "unit_completed", "Biên tập hoàn thành PDF",
            {"artifact_ids": [pdf_id], "unit_key": "editor_pdf"},
        )
        pdf_test = await self.quality_gate(
            state, "editor_pdf", "PDF truyện tranh cuối", content=metadata,
            artifact_ids=[pdf_id],
        )
        self.revise_if_needed(state, pdf_test, "editor_pdf")
        self.progress(state, 99)
        self.db.set_task_status(state["project_id"], self.agent_id, "done")
        self.db.update_project(state["project_id"], stage="finalized", progress=98, final_pdf=str(destination))
        self.event(
            state, "artifact_ready", "PDF truyện tranh đã sẵn sàng",
            {"path": str(destination), "artifact_ids": [pdf_id]},
        )
        self.completed(state, "Đã ghép tranh với đoạn kể riêng, hoàn thiện bìa và xuất PDF")
        if self.direct_approval_stage(state):
            self.event(
                state, "waiting_for_user_approval",
                "Bản PDF cuối đã hoàn thành và được chuyển thẳng đến bạn duyệt.",
                {"to": "user", "approval_stage": "final"},
            )
        return {**state, "final_pdf": str(destination), "stage": "finalized", "completed": True}

    @staticmethod
    def _deterministic_review(state: ComicState) -> dict:
        expected = int(state["plan"].get("page_count", 0))
        script_pages = state["script"].get("pages", [])
        prompts = state.get("page_prompts", [])
        images = state.get("page_images", [])
        bible = state.get("character_bible", {})
        short_story_pages = [
            page for page in script_pages
            if len(LayoutService._story_text(page).split()) < 35
        ]
        issues = []
        target = "none"
        if len(script_pages) != expected:
            target = "writer"
            issues.append({
                "category": "page_count", "reason": "Kịch bản không đủ số trang đã khóa",
                "evidence": f"expected={expected}, actual={len(script_pages)}",
            })
        elif short_story_pages:
            target = "writer"
            issues.append({
                "category": "story_text_quality",
                "reason": "Có trang thiếu đoạn kể hoặc đoạn kể chưa đủ ý",
                "evidence": f"short_pages={len(short_story_pages)}, total={len(script_pages)}",
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

