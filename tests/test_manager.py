import asyncio
from pathlib import Path

from backend.app.db import Database
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
