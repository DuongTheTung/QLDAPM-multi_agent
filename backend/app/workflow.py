from __future__ import annotations

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
        images = ImageService(settings, router)
        common = {"db": db, "router": router, "artifacts_root": settings.artifacts_dir}
        self.pm = PMAgent(**common)
        self.consultants = ConsultantCoordinator(**common)
        self.writer = WriterAgent(**common)
        self.designer = DesignerAgent(**common, image_service=images)
        self.artist = ArtistAgent(**common, image_service=images)
        self.editor = EditorAgent(**common, layout=LayoutService(), settings=settings)
        self.graph = self._build()

    def _build(self):
        graph = StateGraph(ComicState)
        graph.add_node("pm", self.pm.run)
        graph.add_node("consultants", self.consultants.run)
        graph.add_node("writer", self.writer.run)
        graph.add_node("designer", self.designer.run)
        graph.add_node("artist", self.artist.run)
        graph.add_node("editor", self.editor.run)
        graph.add_conditional_edges(
            START,
            self._entry_route,
            {"pm": "pm", "consultants": "consultants", "writer": "writer", "designer": "designer", "artist": "artist", "editor": "editor"},
        )
        graph.add_conditional_edges("pm", self._after_pm, {"consultants": "consultants", "end": END})
        graph.add_edge("consultants", "writer")
        graph.add_edge("writer", "designer")
        graph.add_edge("designer", "artist")
        graph.add_edge("artist", "editor")
        graph.add_conditional_edges(
            "editor",
            self._after_editor,
            {"pm": "pm", "writer": "writer", "designer": "designer", "artist": "artist", "editor": "editor"},
        )
        return graph.compile(checkpointer=MemorySaver())

    @staticmethod
    def _entry_route(state: ComicState) -> Literal["pm", "consultants", "writer", "designer", "artist", "editor"]:
        stage = state.get("stage", "brief")
        return {
            "brief": "pm", "planning": "pm", "script": "consultants",
            "character_design": "designer", "illustration": "artist",
            "review": "editor", "layout": "editor", "finalized": "pm",
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
        return latest

