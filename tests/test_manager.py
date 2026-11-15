import asyncio
from pathlib import Path
from types import SimpleNamespace

from backend.app.db import Database
from backend.app.exceptions import AutomaticRevision
from backend.app.manager import WorkflowManager


class SlowWorkflow:
    async def run(self, state):
        await asyncio.Event().wait()


async def test_stop_cancels_running_workflow_and_persists_status(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    manager = WorkflowManager(database, SlowWorkflow())

    manager.start("project-1", {"project_id": "project-1"})
    await asyncio.sleep(0)

    assert await manager.stop("project-1") is True
    assert database.get_project("project-1")["status"] == "stopped"
    assert "project-1" not in manager.running
    assert database.get_events("project-1")[-1]["event_type"] == "workflow_stopped"


async def test_pause_sets_cooperative_request_without_cancelling(tmp_path: Path):
    database = Database(tmp_path / "pause.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    manager = WorkflowManager(database, SlowWorkflow())

    manager.start("project-1", {"project_id": "project-1"})
    await asyncio.sleep(0)
    assert manager.pause("project-1") is True
    project = database.get_project("project-1")
    assert project["status"] == "pause_requested"
    assert project["pause_requested"] is True
    assert "project-1" in manager.running
    await manager.stop("project-1")


async def test_failed_review_is_reassigned_then_bypassed_instead_of_failing(tmp_path: Path):
    class RevisionWorkflow:
        settings = SimpleNamespace(max_revisions=1)

        def __init__(self):
            self.calls = 0

        async def run(self, state):
            self.calls += 1
            if "artist_page_1" not in state.get("review_bypass", []):
                raise AutomaticRevision("artist", "artist_page_1", "Ảnh trang 1 cần làm lại")

    database = Database(tmp_path / "revision.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    workflow = RevisionWorkflow()
    manager = WorkflowManager(database, workflow)

    await manager._run("project-1", {"project_id": "project-1", "stage": "illustration"})

    project = database.get_project("project-1")
    event_types = [event["event_type"] for event in database.get_events("project-1")]
    assert project["status"] == "running"
    assert project["error"] is None
    assert workflow.calls == 3
    assert "revision_assigned" in event_types
    assert "quality_override" in event_types
    assert "workflow_failed" not in event_types
