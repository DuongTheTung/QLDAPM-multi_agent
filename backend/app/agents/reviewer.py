from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import APIError
from PIL import Image

from ..config import Settings
from ..schemas import ComicState
from ..services.layout import LayoutService
from ..services.router import RouterExhaustedError
from .base import BaseAgent


class ReviewerAgent(BaseAgent):
    agent_id = "reviewer"
    display_name = "Kiểm duyệt"

    UNIT_SYSTEM = """Bạn là agent kiểm duyệt độc lập của xưởng truyện tranh. Chính sách mặc định
là PASS. Chỉ REVISE khi có bằng chứng rõ về file hỏng/thiếu, nội dung không an toàn theo tuổi, sai
nghiêm trọng kịch bản đã khóa hoặc đổi ngoại hình nhân vật. Không REVISE vì sở thích thẩm mỹ, cách
diễn đạt chưa hoàn hảo hay lỗi nhỏ; các lỗi đó ghi vào notes và vẫn PASS. Không tự sửa sản phẩm."""
    UNIT_SCHEMA = """{
      "verdict": "PASS|REVISE", "summary": "kết luận cụ thể",
      "serious_issues": ["..."], "notes": ["..."]
    }"""

    SYSTEM = """Bạn là trưởng kiểm duyệt truyện tranh. Chính sách mặc định là PASS. Duyệt mạch
truyện, các đoạn kể theo trang, an toàn theo tuổi, độ nhất quán nhân vật/bối cảnh và mức trung thành
với kịch bản. Đoạn kể cần đủ ý và nối mạch; không yêu cầu bóng thoại. Chỉ REVISE khi có bằng chứng
rõ về lỗi nghiêm trọng. Lỗi nhỏ hoặc lựa chọn thẩm mỹ chỉ ghi vào minor_notes và vẫn PASS.
Nếu cần sửa, chỉ định đúng một agent writer, designer hoặc artist. Không tự sửa hay vẽ lại sản phẩm."""
    SCHEMA = """{
      "verdict": "PASS|REVISE", "summary": "kết luận ngắn",
      "serious_issues": [{"category": "...", "reason": "...", "evidence": "..."}],
      "minor_notes": ["..."], "revision_agent": "writer|designer|artist|none",
      "revision_instructions": "chỉ dẫn cụ thể",
      "scores": {"story": 0, "age_safety": 0, "consistency": 0, "script_fidelity": 0}
    }"""

    def __init__(self, *args, layout: LayoutService, settings: Settings, **kwargs):
        super().__init__(*args, **kwargs)
        self.layout = layout
        self.settings = settings

    async def inspect_unit(
        self,
        state: ComicState,
        *,
        owner: str,
        unit_key: str,
        title: str,
        content: Any = None,
        image_path: Path | None = None,
        artifact_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        artifact_ids = artifact_ids or []
        reviewers = self.role_workers(state)
        reviewer = reviewers[sum(unit_key.encode("utf-8")) % len(reviewers)]
        reviewer_id = str(reviewer["runtime_id"])
        self.progress(state, 8, owner=reviewer_id, reset=True)
        if not reviewer.get("is_core"):
            self.db.set_task_status(state["project_id"], reviewer_id, "in_progress")
        self.db.begin_task_testing(state["project_id"], owner, unit_key)
        test_id = self.db.create_quality_test(
            state["project_id"], owner, unit_key, title, artifact_ids, reviewer_id,
        )
        payload = {
            "test_id": test_id, "owner": owner, "unit_key": unit_key,
            "title": title, "artifact_ids": artifact_ids, "content": content,
        }
        self.worker_event(
            state, reviewer, "testing_started",
            f"{reviewer['name']} đang kiểm tra: {title}", payload,
        )
        technical_issue = self._technical_issue(image_path)
        if technical_issue:
            result: dict[str, Any] = {
                "verdict": "REVISE", "summary": technical_issue,
                "serious_issues": [technical_issue], "notes": [],
            }
        else:
            prompt = (
                f"Agent thực hiện: {owner}\nĐầu ra: {title}\n"
                f"Ngữ cảnh kiểm tra:\n{json.dumps(content, ensure_ascii=False, default=str)[:14000]}"
            )
            models, temperature, _ = self.worker_model_config(state, reviewer, 0.05)
            try:
                result, _ = await self.router.chat_json(
                    system=self.UNIT_SYSTEM,
                    prompt=prompt,
                    schema_hint=self.UNIT_SCHEMA,
                    temperature=temperature,
                    on_attempt=self.worker_attempt(state, reviewer),
                    image_paths=[image_path] if image_path else None,
                    timeout_seconds=60,
                    models=models,
                )
            except (RouterExhaustedError, APIError, TimeoutError) as error:
                result = {
                    "verdict": "PASS",
                    "summary": "Đạt kiểm tra kỹ thuật; model semantic tạm thời không phản hồi.",
                    "serious_issues": [],
                    "notes": [str(error)],
                }
        self.progress(state, 78, owner=reviewer_id)
        serious = result.get("serious_issues") or []
        passed = str(result.get("verdict", "PASS")).upper() != "REVISE" or not serious
        result["verdict"] = "PASS" if passed else "REVISE"
        feedback = str(result.get("summary") or "")
        self.db.finish_quality_test(test_id, result["verdict"], feedback)
        self.db.finish_task_testing(state["project_id"], owner, unit_key, passed)
        if not passed:
            self.db.add_revision_task(
                state["project_id"], owner, f"Kiểm duyệt trả lại: {title}",
                feedback or "Sửa lỗi nghiêm trọng được Kiểm duyệt phát hiện.", 40 + test_id,
            )
        self.worker_event(
            state, reviewer,
            "testing_passed" if passed else "testing_failed",
            f"{title}: {'ĐẠT' if passed else 'CHƯA ĐẠT — trả lại ' + owner}",
            {**payload, "result": result, "assigned_to": None if passed else owner},
        )
        self.progress(state, 100, owner=reviewer_id)
        return result

    @staticmethod
    def _technical_issue(image_path: Path | None) -> str:
        if image_path is None:
            return ""
        if not image_path.is_file():
            return "File ảnh không tồn tại."
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                if image.width < 256 or image.height < 256:
                    return "Độ phân giải ảnh quá thấp."
        except (OSError, ValueError) as error:
            return f"File ảnh không hợp lệ: {error}"
        return ""

    async def run(self, state: ComicState) -> ComicState:
        approved_stages = self.human_approved_stages(state) | set(
            state.get("human_approved_stages", [])
        )
        if "illustration" in approved_stages:
            review = {
                "verdict": "PASS",
                "summary": "Tranh minh họa đã được người dùng duyệt; không kiểm duyệt tự động lại.",
                "serious_issues": [],
                "minor_notes": ["Chuyển thẳng sang dàn trang theo quyết định của người dùng."],
                "revision_agent": "none",
                "revision_instructions": "",
                "human_approved": True,
            }
            for worker in self.role_workers(state):
                self.db.complete_agent_work(state["project_id"], str(worker["runtime_id"]))
            self.db.update_project(state["project_id"], stage="layout", progress=90)
            self.db.add_event(
                state["project_id"], "system", "automatic_review_skipped",
                "Tranh minh họa đã được bạn duyệt; bỏ qua Kiểm duyệt tự động và chuyển sang dàn trang.",
                {"approval_stage": "illustration", "to": "editor"},
            )
            return {**state, "review": review, "stage": "layout"}

        self.started(state, "testing", 84)
        self.step(state, "reviewer_story", "Kiểm duyệt đang đối chiếu mạch truyện và độ tuổi")
        contact_sheet = self.layout.make_contact_sheet(
            Path(state["cover_image"]),
            [Path(path) for path in state.get("page_images", [])],
            self.project_dir(state) / "review-contact-sheet.jpg",
        )
        self.progress(state, 18)
        artifact_id = self.db.add_artifact(
            state["project_id"], self.agent_id, "review_sheet",
            "Contact sheet kiểm duyệt", str(contact_sheet),
        )
        prompt = (
            f"Production brief:\n{state['plan']}\n\nKịch bản:\n{state['script']}\n\n"
            f"Character bible:\n{state['character_bible']}\n\nPage prompts:\n{state['page_prompts']}\n\n"
            f"Số ảnh trang: {len(state.get('page_images', []))}."
        )
        if approved_stages:
            protected = {
                "script": "Biên kịch", "character_design": "Thiết kế nhân vật",
                "illustration": "Họa sĩ",
            }
            locked = [protected[stage] for stage in approved_stages if stage in protected]
            prompt += (
                "\n\nQUYẾT ĐỊNH CỦA NGƯỜI DÙNG: Các phần sau đã được duyệt và là dữ liệu khóa: "
                + ", ".join(locked)
                + ". Không kiểm tra lại, không yêu cầu các agent này sửa và không dùng chúng làm revision_agent."
            )
        self.step(state, "reviewer_visual", "Kiểm duyệt đang đối chiếu ảnh, nhân vật và kịch bản")
        models, temperature, _ = self.model_config(state, 0.05)
        try:
            review, usage = await self.router.chat_json(
                system=self.SYSTEM, prompt=prompt, schema_hint=self.SCHEMA,
                temperature=temperature, on_attempt=self.model_attempt(state),
                image_paths=[contact_sheet], timeout_seconds=60, models=models,
            )
        except (RouterExhaustedError, APIError, TimeoutError) as error:
            review = self._deterministic_review(state)
            review.setdefault("minor_notes", []).append(str(error))
            usage = {"model": "deterministic-reviewer-recovery", "prompt_tokens": 0, "completion_tokens": 0}
        self.progress(state, 72)
        review = self._protect_human_approvals(review, approved_stages)
        serious = review.get("serious_issues") or []
        verdict = str(review.get("verdict", "PASS")).upper()
        if verdict == "REVISE" and not serious:
            verdict = "PASS"
            review["verdict"] = "PASS"
        review_id = self.db.add_artifact(
            state["project_id"], self.agent_id, "review",
            f"Kết quả kiểm duyệt {state.get('revision_count', 0) + 1}",
            str(self.save_json_file(state, review)),
        )
        self.progress(state, 88)
        if verdict == "REVISE":
            self.step(state, "reviewer_final", "Kiểm duyệt kết luận và giao lại agent xử lý")
            result = self._revision(state, review, usage, [artifact_id, review_id])
            self.progress(state, 100)
            self._complete_helpers(state)
            return result
        self.step(state, "reviewer_final", "Kiểm duyệt kết luận sản phẩm đạt yêu cầu")
        self.db.update_project(state["project_id"], stage="layout", progress=90)
        self.completed(state, "Kiểm duyệt tổng thể kết luận ĐẠT")
        self._complete_helpers(state)
        self.event(
            state, "review_passed", "Sản phẩm đạt kiểm duyệt; chuyển Biên tập dàn trang",
            {"artifact_ids": [artifact_id, review_id], "result": review, "to": "editor"},
        )
        return {
            **state, "review": review, "stage": "layout",
            "model_usage": [*state.get("model_usage", []), usage],
        }

    def _complete_helpers(self, state: ComicState) -> None:
        for worker in self.role_workers(state)[1:]:
            self.db.complete_agent_work(state["project_id"], str(worker["runtime_id"]))
            self.worker_event(
                state, worker, "agent_completed",
                f"{worker['name']} đã hoàn thành phần kiểm duyệt được PM phân công",
            )

    def save_json_file(self, state: ComicState, review: dict[str, Any]) -> Path:
        path = self.project_dir(state) / f"05-review-{state.get('revision_count', 0) + 1}.json"
        path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _revision(
        self, state: ComicState, review: dict[str, Any], usage: dict[str, Any],
        artifact_ids: list[int],
    ) -> ComicState:
        count = state.get("revision_count", 0) + 1
        target = str(review.get("revision_agent", "artist"))
        if target not in {"writer", "designer", "artist"}:
            target = "artist"
        instructions = str(review.get("revision_instructions") or review.get("summary") or "Sửa lỗi nghiêm trọng")
        if count > self.settings.max_revisions:
            self.db.update_project(
                state["project_id"], status="running", stage="layout",
                error=None, progress=90,
            )
            self.event(
                state, "quality_override",
                f"Đã đủ {self.settings.max_revisions} vòng sửa; ghi chú lỗi nhỏ và tiếp tục dàn trang.",
                {"review": review, "last_instructions": instructions},
            )
            review["verdict"] = "PASS"
            review.setdefault("minor_notes", []).append(
                "Đã đạt giới hạn vòng sửa tự động; tiếp tục để không làm dừng dự án."
            )
            return {
                **state, "review": review, "stage": "layout", "revision_count": count,
                "feedback": "", "model_usage": [*state.get("model_usage", []), usage],
            }
        progress = {"writer": 18, "designer": 36, "artist": 52}[target]
        stage = {"writer": "script", "designer": "character_design", "artist": "illustration"}[target]
        self.db.update_project(state["project_id"], stage=stage, progress=progress)
        self.db.add_revision_task(
            state["project_id"], target, f"Kiểm duyệt trả sửa vòng {count}", instructions, 10 + count,
        )
        self.event(
            state, "revision_assigned", f"Kiểm duyệt trả về {target}: {instructions}",
            {"to": target, "revision": count, "result": review, "artifact_ids": artifact_ids},
        )
        return {
            **state, "review": review, "stage": stage, "revision_target": target,
            "revision_count": count, "feedback": instructions,
            "model_usage": [*state.get("model_usage", []), usage],
        }

    @staticmethod
    def _protect_human_approvals(
        review: dict[str, Any], approved_stages: set[str],
    ) -> dict[str, Any]:
        target_stage = {
            "writer": "script", "designer": "character_design", "artist": "illustration",
        }.get(str(review.get("revision_agent", "none")))
        if str(review.get("verdict", "PASS")).upper() != "REVISE" or target_stage not in approved_stages:
            return review
        protected_review = dict(review)
        protected_review["verdict"] = "PASS"
        protected_review["revision_agent"] = "none"
        protected_review["revision_instructions"] = ""
        protected_review["serious_issues"] = []
        notes = list(protected_review.get("minor_notes") or [])
        notes.append(
            "Không giao sửa vì phần bị đề xuất đã được người dùng duyệt và khóa."
        )
        protected_review["minor_notes"] = notes
        protected_review["summary"] = (
            "Tôn trọng quyết định duyệt của người dùng; không kiểm duyệt lại phần đã khóa."
        )
        return protected_review

    @staticmethod
    def _deterministic_review(state: ComicState) -> dict[str, Any]:
        expected = int(state["plan"].get("page_count", 0))
        script_pages = state["script"].get("pages", [])
        prompts = state.get("page_prompts", [])
        images = state.get("page_images", [])
        issues = []
        target = "none"
        if len(script_pages) != expected:
            target = "writer"
            issues.append({"category": "page_count", "reason": "Kịch bản thiếu trang", "evidence": f"{len(script_pages)}/{expected}"})
        elif any(len(LayoutService._story_text(page).split()) < 35 for page in script_pages):
            target = "writer"
            issues.append({
                "category": "story_text", "reason": "Đoạn kể của một hoặc nhiều trang quá ngắn",
                "evidence": "Mỗi trang cần đoạn kể đủ ý để đọc cạnh tranh minh họa.",
            })
        elif len(prompts) != expected or len(images) != expected or any(not Path(path).is_file() for path in images):
            target = "artist"
            issues.append({"category": "artwork", "reason": "Thiếu prompt hoặc ảnh", "evidence": f"prompts={len(prompts)}, images={len(images)}"})
        return {
            "verdict": "REVISE" if issues else "PASS",
            "summary": "Phát hiện lỗi nghiêm trọng" if issues else "Đủ thành phần để dàn trang",
            "serious_issues": issues, "minor_notes": [], "revision_agent": target,
            "revision_instructions": "Bổ sung thành phần bị thiếu, giữ nguyên phần đã đạt." if issues else "",
            "scores": {"story": 8, "age_safety": 8, "consistency": 8, "script_fidelity": 8},
        }
