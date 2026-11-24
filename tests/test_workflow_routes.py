from backend.app.agents.base import BaseAgent
from backend.app.agents.pm import PMAgent
from backend.app.agents.reviewer import ReviewerAgent
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
        "pm_scope", "writer_story_text", "designer_references",
        "artist_pages", "reviewer_final", "editor_pdf",
    }
    assert any("8" in item["title"] for item in children if item["agent"] == "artist")


def test_pm_keeps_six_workflow_lanes_and_assigns_named_role_workers():
    helper = {
        "id": "custom-artist-1", "name": "An", "role": "Họa sĩ",
        "role_key": "artist",
    }
    tasks = PMAgent._schedule("project-123", 8, [helper])
    parents = [item for item in tasks if item["item_type"] == "task"]
    helper_tasks = [item for item in tasks if item["agent"] == helper["id"]]

    assert len(parents) == 6
    assert len(helper_tasks) == 1
    assert helper_tasks[0]["parent_id"].endswith("-ART")
    assert "An" in helper_tasks[0]["title"]


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


async def test_selected_human_approval_skips_automatic_unit_review(tmp_path):
    class WriterForTest(BaseAgent):
        agent_id = "writer"
        display_name = "Biên kịch"

    database = Database(tmp_path / "direct-human-approval.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    database.update_project(
        "project-1", approval_enabled=True, approval_stages=["script"],
    )
    agent = WriterForTest(database, object(), tmp_path)

    result = await agent.quality_gate(
        {"project_id": "project-1"}, "writer_pages", "Kịch bản phân trang",
        content={"pages": []},
    )

    assert result["verdict"] == "PASS"
    assert database.list_quality_tests("project-1") == []
    event = database.get_events("project-1")[-1]
    assert event["event_type"] == "waiting_for_user_approval"
    assert "chuyển thẳng đến bạn duyệt" in event["message"]


async def test_unselected_stage_is_sent_to_reviewer_immediately(tmp_path):
    class WriterForTest(BaseAgent):
        agent_id = "writer"
        display_name = "Biên kịch"

    class ReviewerForTest:
        called = False

        async def inspect_unit(self, *_args, **_kwargs):
            self.called = True
            return {"verdict": "PASS", "serious_issues": [], "notes": []}

    database = Database(tmp_path / "automatic-review.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    database.update_project(
        "project-1", approval_enabled=True,
        approval_stages=["character_design", "illustration", "final"],
    )
    agent = WriterForTest(database, object(), tmp_path)
    reviewer = ReviewerForTest()
    agent.reviewer = reviewer

    result = await agent.quality_gate(
        {"project_id": "project-1"}, "writer_pages", "Kịch bản phân trang",
        content={"pages": []},
    )

    assert result["verdict"] == "PASS"
    assert reviewer.called is True
    assert not any(
        event["event_type"] == "waiting_for_user_approval"
        for event in database.get_events("project-1")
    )


def test_reviewer_cannot_return_a_human_approved_stage():
    review = {
        "verdict": "REVISE",
        "summary": "Đề nghị thiết kế lại",
        "serious_issues": [{"category": "style", "reason": "test"}],
        "minor_notes": [],
        "revision_agent": "designer",
        "revision_instructions": "Làm lại thiết kế",
    }

    protected = ReviewerAgent._protect_human_approvals(
        review, {"character_design"},
    )

    assert protected["verdict"] == "PASS"
    assert protected["revision_agent"] == "none"
    assert protected["serious_issues"] == []
    assert "người dùng duyệt" in protected["minor_notes"][-1]


async def test_human_approved_illustration_bypasses_aggregate_reviewer(tmp_path):
    database = Database(tmp_path / "approved-illustration.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    approval = database.create_approval(
        "project-1", "illustration", "illustration:v1", {"page_images": ["page-1.png"]},
    )
    database.resolve_approval("project-1", approval["id"], "approved")
    reviewer = ReviewerAgent(
        database, object(), tmp_path, layout=object(), settings=object(),
    )

    result = await reviewer.run({"project_id": "project-1", "stage": "testing"})

    assert result["stage"] == "layout"
    assert result["review"]["human_approved"] is True
    events = database.get_events("project-1")
    assert events[-1]["event_type"] == "automatic_review_skipped"
    assert not any(event["event_type"] == "agent_started" for event in events)


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

