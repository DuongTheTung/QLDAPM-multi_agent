from __future__ import annotations

import hashlib
import json
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import (
    ArtistAgent,
    ConsultantCoordinator,
    DesignerAgent,
    EditorAgent,
    PMAgent,
    ReviewerAgent,
    WriterAgent,
)
from .config import Settings
from .db import Database
from .schemas import ComicState
from .services.images import ImageService
from .services.layout import LayoutService
from .services.router import NineRouterClient


class ComicWorkflow:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        router = NineRouterClient(settings)
        self.router = router
        images = ImageService(settings, router)
        common = {"db": db, "router": router, "artifacts_root": settings.artifacts_dir}
        self.pm = PMAgent(**common)
        self.consultants = ConsultantCoordinator(**common)
        self.writer = WriterAgent(**common)
        self.designer = DesignerAgent(**common, image_service=images)
        self.artist = ArtistAgent(**common, image_service=images)
        self.reviewer = ReviewerAgent(
            **common, layout=LayoutService(), settings=settings,
        )
        self.editor = EditorAgent(**common, layout=LayoutService(), settings=settings)
        for agent in (self.pm, self.writer, self.designer, self.artist, self.editor):
            agent.reviewer = self.reviewer
        self.graph = self._build()

    def _build(self):
        graph = StateGraph(ComicState)
        graph.add_node("pm", self.pm.run)
        graph.add_node("consultants", self.consultants.run)
        graph.add_node("writer", self.writer.run)
        graph.add_node("designer", self.designer.run)
        graph.add_node("artist", self.artist.run)
        graph.add_node("reviewer", self.reviewer.run)
        graph.add_node("editor", self.editor.run)
        graph.add_conditional_edges(
            START,
            self._entry_route,
            {"pm": "pm", "consultants": "consultants", "writer": "writer", "designer": "designer", "artist": "artist", "reviewer": "reviewer", "editor": "editor"},
        )
        graph.add_conditional_edges("pm", self._after_pm, {"consultants": "consultants", "end": END})
        graph.add_edge("consultants", "writer")
        graph.add_edge("writer", "designer")
        graph.add_edge("designer", "artist")
        graph.add_edge("artist", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            self._after_reviewer,
            {"writer": "writer", "designer": "designer", "artist": "artist", "editor": "editor", "pm": "pm"},
        )
        graph.add_conditional_edges(
            "editor",
            self._after_editor,
            {"pm": "pm", "writer": "writer", "designer": "designer", "artist": "artist", "editor": "editor"},
        )
        return graph.compile(checkpointer=MemorySaver())

    @staticmethod
    def _entry_route(state: ComicState) -> Literal["pm", "consultants", "writer", "designer", "artist", "reviewer", "editor"]:
        stage = state.get("stage", "brief")
        return {
            "brief": "pm", "planning": "pm", "script": "consultants",
            "character_design": "designer", "illustration": "artist",
            "testing": "reviewer", "review": "reviewer", "layout": "editor", "finalized": "pm",
            "needs_attention": "pm",
        }.get(stage, "pm")  # type: ignore[return-value]

    @staticmethod
    def _after_pm(state: ComicState) -> Literal["consultants", "end"]:
        return "end" if state.get("completed") else "consultants"

    @staticmethod
    def _after_editor(state: ComicState) -> Literal["pm", "writer", "designer", "artist", "editor"]:
        return {
            "script": "writer", "character_design": "designer", "illustration": "artist",
            "layout": "editor", "finalized": "pm", "needs_attention": "pm",
        }.get(state.get("stage", "review"), "editor")  # type: ignore[return-value]

    @staticmethod
    def _after_reviewer(state: ComicState) -> Literal["pm", "writer", "designer", "artist", "editor"]:
        return {
            "script": "writer", "character_design": "designer", "illustration": "artist",
            "layout": "editor", "needs_attention": "pm",
        }.get(state.get("stage", "testing"), "editor")  # type: ignore[return-value]

    async def run(self, state: ComicState) -> ComicState:
        project_id = state["project_id"]
        latest = state
        config = {"configurable": {"thread_id": project_id}, "recursion_limit": 30}
        async for snapshot in self.graph.astream(state, config=config, stream_mode="values"):
            latest = snapshot
            self.db.update_project(
                project_id,
                state_json=json.dumps(snapshot, ensure_ascii=False),
                stage=snapshot.get("stage", "running"),
            )
            project = self.db.get_project(project_id)
            if project and project.get("pause_requested"):
                self.db.update_project(
                    project_id, status="paused", pause_requested=False, error=None,
                )
                self.db.add_event(
                    project_id, "system", "workflow_paused",
                    "Đã tạm dừng tại điểm lưu an toàn; bạn có thể can thiệp công việc.",
                    {"stage": snapshot.get("stage")},
                )
                break
            if project and self._request_approval(project, snapshot):
                break
        return latest

    @staticmethod
    def _approval_content(state: ComicState) -> tuple[str, str, dict] | None:
        stage = state.get("stage")
        if stage == "character_design" and state.get("script"):
            return "script", "writer", {"script": state["script"]}
        if stage == "illustration" and state.get("character_bible"):
            return "character_design", "designer", {
                "character_bible": state["character_bible"],
            }
        if stage in {"testing", "review"} and state.get("page_prompts"):
            return "illustration", "artist", {
                "page_prompts": state["page_prompts"],
                "page_images": state.get("page_images", []),
                "cover_image": state.get("cover_image", ""),
            }
        if stage == "finalized" and state.get("final_pdf"):
            return "final", "editor", {
                "review": state.get("review", {}), "final_pdf": state["final_pdf"],
            }
        return None

    def _request_approval(self, project: dict, state: ComicState) -> bool:
        if not project.get("approval_enabled"):
            return False
        candidate = self._approval_content(state)
        if not candidate:
            return False
        stage, owner, content = candidate
        if stage not in project.get("approval_stages", []):
            return False
        serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]
        signature = f"{stage}:{state.get('revision_count', 0)}:{digest}"
        previous = self.db.get_approval_by_signature(project["id"], signature)
        if previous:
            return previous["status"] == "pending"
        approval = self.db.create_approval(project["id"], stage, signature, content)
        event_id = self.db.add_event(
            project["id"], owner, "approval_requested",
            f"Nội dung {stage} đang chờ bạn duyệt.",
            {"approval_id": approval["id"], "approval_stage": stage},
        )
        self.db.link_approval_event(project["id"], approval["id"], event_id)
        self.db.update_project(project["id"], status="awaiting_approval", error=None)
        return True

