from backend.app.agents.pm import PMAgent
from backend.app.db import Database
from backend.app.workflow import ComicWorkflow


def test_entry_routes_by_persisted_stage():
    assert ComicWorkflow._entry_route({"stage": "brief"}) == "pm"
    assert ComicWorkflow._entry_route({"stage": "script"}) == "consultants"
    assert ComicWorkflow._entry_route({"stage": "character_design"}) == "designer"
    assert ComicWorkflow._entry_route({"stage": "illustration"}) == "artist"
    assert ComicWorkflow._entry_route({"stage": "review"}) == "reviewer"
    assert ComicWorkflow._entry_route({"stage": "testing"}) == "reviewer"


def test_pm_builds_specific_task_and_subtask_hierarchy():
    tasks = PMAgent._schedule("project-123", 8)
    parents = [item for item in tasks if item["item_type"] == "task"]
    children = [item for item in tasks if item["item_type"] == "subtask"]

    assert len(parents) == 6
    assert len(children) == 18
    assert all(item["parent_id"] for item in children)
    assert {item["step_key"] for item in children} >= {
        "pm_scope", "writer_dialogue", "designer_references",
        "artist_pages", "reviewer_final", "editor_pdf",
    }
    assert any("8" in item["title"] for item in children if item["agent"] == "artist")


def test_editor_routes_revision_to_owner():
    assert ComicWorkflow._after_editor({"stage": "script"}) == "writer"
    assert ComicWorkflow._after_editor({"stage": "character_design"}) == "designer"
    assert ComicWorkflow._after_editor({"stage": "illustration"}) == "artist"
    assert ComicWorkflow._after_editor({"stage": "layout"}) == "editor"
    assert ComicWorkflow._after_editor({"stage": "finalized"}) == "pm"


def test_reviewer_routes_failed_output_back_to_owner_or_layout():
    assert ComicWorkflow._after_reviewer({"stage": "script"}) == "writer"
    assert ComicWorkflow._after_reviewer({"stage": "character_design"}) == "designer"
    assert ComicWorkflow._after_reviewer({"stage": "illustration"}) == "artist"
    assert ComicWorkflow._after_reviewer({"stage": "layout"}) == "editor"


def test_optional_approval_gate_is_versioned_and_persisted(tmp_path):
    database = Database(tmp_path / "approval.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    database.update_project(
        "project-1", approval_enabled=True, approval_stages=["script"],
    )
    workflow = ComicWorkflow.__new__(ComicWorkflow)
    workflow.db = database
    state = {
        "project_id": "project-1", "stage": "character_design",
        "script": {"pages": [{"page_number": 1}]}, "revision_count": 0,
    }

    assert workflow._request_approval(database.get_project("project-1"), state) is True
    assert database.get_project("project-1")["status"] == "awaiting_approval"
    approval = database.list_approvals("project-1")[0]
    assert approval["stage"] == "script"
    assert database.get_events("project-1")[-1]["event_type"] == "approval_requested"

    database.resolve_approval("project-1", approval["id"], "approved")
    assert workflow._request_approval(database.get_project("project-1"), state) is False


async def test_workflow_honors_pause_at_next_safe_snapshot(tmp_path):
    class FakeGraph:
        async def astream(self, state, **_):
            yield {**state, "stage": "character_design", "script": {"pages": []}}

    database = Database(tmp_path / "safe-pause.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    database.update_project(
        "project-1", status="pause_requested", pause_requested=True,
    )
    workflow = ComicWorkflow.__new__(ComicWorkflow)
    workflow.db = database
    workflow.graph = FakeGraph()

    await workflow.run({"project_id": "project-1", "stage": "script"})

    project = database.get_project("project-1")
    assert project["status"] == "paused"
    assert project["pause_requested"] is False
    assert database.get_events("project-1")[-1]["event_type"] == "workflow_paused"

