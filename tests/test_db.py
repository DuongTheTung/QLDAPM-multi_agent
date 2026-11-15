from pathlib import Path

from backend.app.db import Database


def test_delete_project_removes_related_records(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    database.add_event("project-1", "pm", "started", "Started")
    database.add_artifact("project-1", "writer", "script", "script.json", "script.json")

    assert database.delete_project("project-1") is True
    assert database.get_project("project-1") is None
    assert database.get_events("project-1") == []
    assert database.get_artifacts("project-1") == []
    assert database.delete_project("project-1") is False


def test_project_agents_include_six_core_and_manage_custom_agent(tmp_path: Path):
    database = Database(tmp_path / "agents.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")

    agents = database.list_project_agents("project-1")
    assert len(agents) == 6
    assert all(agent["is_core"] for agent in agents)

    custom = database.create_project_agent(
        "project-1", "An Toàn", "reviewer", "Kiểm tra nội dung phù hợp trẻ em.",
        "#557a68", "cx/gpt-5.6-sol", ["ag/gemini-3.8-flash-medium"], 0.3,
    )
    assert custom["model"] == "cx/gpt-5.6-sol"
    assert custom["fallback_models"] == ["ag/gemini-3.8-flash-medium"]
    assert custom["temperature"] == 0.3
    assert custom["role_key"] == "reviewer"
    assert custom["role"] == "Kiểm duyệt"
    workers = database.role_workers("project-1", "reviewer")
    assert [worker["runtime_id"] for worker in workers] == ["reviewer", custom["id"]]
    assert len(database.list_project_agents("project-1")) == 7
    assert database.update_project_agent("project-1", custom["id"], enabled=False)
    assert database.get_project_agent("project-1", custom["id"])["enabled"] is False
    assert database.delete_project_agent("project-1", custom["id"])
    assert len(database.list_project_agents("project-1")) == 6


def test_core_agent_model_config_and_approval_audit(tmp_path: Path):
    database = Database(tmp_path / "settings.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")

    assert database.update_project_agent(
        "project-1", "project-1:writer", model="cx/custom",
        fallback_models=["ag/fallback"], temperature=0.55,
    )
    writer = database.get_project_agent("project-1", "project-1:writer")
    assert writer["model"] == "cx/custom"
    assert writer["fallback_models"] == ["ag/fallback"]
    assert writer["temperature"] == 0.55

    database.update_project(
        "project-1", approval_enabled=True, approval_stages=["script", "final"],
    )
    project = database.get_project("project-1")
    assert project["approval_enabled"] is True
    assert project["approval_stages"] == ["script", "final"]

    approval = database.create_approval(
        "project-1", "script", "script:0:hash", {"script": {"pages": []}},
    )
    assert approval["status"] == "pending"
    assert database.resolve_approval("project-1", approval["id"], "approved")
    assert database.get_approval("project-1", approval["id"])["status"] == "approved"


def test_agent_steps_keep_parent_and_subtasks_synchronized(tmp_path: Path):
    database = Database(tmp_path / "task-sync.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    base = {
        "agent": "writer", "status": "todo", "start_at": "2026-01-01T00:00:00Z",
        "due_at": "2026-01-01T01:00:00Z", "depends_on": [], "detail": "",
    }
    database.replace_tasks("project-1", [
        {**base, "id": "TASK", "title": "Write", "item_type": "task", "order_index": 0},
        {**base, "id": "SUB-1", "title": "Structure", "item_type": "subtask", "parent_id": "TASK", "step_key": "structure", "order_index": 1},
        {**base, "id": "SUB-2", "title": "Dialogue", "item_type": "subtask", "parent_id": "TASK", "step_key": "dialogue", "order_index": 2},
    ])

    database.start_agent_work("project-1", "writer")
    first = {item["id"]: item["status"] for item in database.get_tasks("project-1")}
    assert first == {"TASK": "in_progress", "SUB-1": "in_progress", "SUB-2": "todo"}

    database.set_task_step("project-1", "writer", "dialogue")
    second = {item["id"]: item["status"] for item in database.get_tasks("project-1")}
    assert second == {"TASK": "in_progress", "SUB-1": "done", "SUB-2": "in_progress"}

    database.complete_agent_work("project-1", "writer")
    assert all(item["status"] == "done" for item in database.get_tasks("project-1"))


def test_global_router_settings_are_persisted(tmp_path: Path):
    database = Database(tmp_path / "router-settings.db")
    database.init()

    assert database.get_app_setting("nine_router") is None
    expected = {
        "models": ["cx/gpt-5.6-sol", "ag/gemini-3.8-flash-medium"],
        "image_model": "ag/gemini-3-pro-image-preview",
    }
    database.set_app_setting("nine_router", expected)

    assert database.get_app_setting("nine_router") == expected


def test_quality_test_moves_task_through_testing_and_keeps_artifact_scope(tmp_path: Path):
    database = Database(tmp_path / "quality.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")
    base = {
        "agent": "artist", "status": "in_progress", "start_at": "2026-01-01T00:00:00Z",
        "due_at": "2026-01-01T01:00:00Z", "depends_on": [], "detail": "",
    }
    database.replace_tasks("project-1", [
        {**base, "id": "ART", "title": "Art", "item_type": "task", "order_index": 0},
        {**base, "id": "PAGE", "title": "Pages", "item_type": "subtask", "parent_id": "ART", "step_key": "artist_pages", "order_index": 1},
    ])
    artifact_id = database.add_artifact(
        "project-1", "artist", "page_raw", "Trang 4", str(tmp_path / "page-04.png"),
    )

    database.begin_task_testing("project-1", "artist", "artist_pages")
    assert {item["id"]: item["status"] for item in database.get_tasks("project-1")} == {
        "ART": "testing", "PAGE": "testing",
    }
    test_id = database.create_quality_test(
        "project-1", "artist", "artist_pages", "Ảnh trang 4", [artifact_id],
    )
    database.finish_quality_test(test_id, "PASS", "Đạt")
    database.finish_task_testing("project-1", "artist", "artist_pages", True)

    result = database.list_quality_tests("project-1")[0]
    assert result["artifact_ids"] == [artifact_id]
    assert result["verdict"] == "PASS"
    assert {item["id"]: item["status"] for item in database.get_tasks("project-1")} == {
        "ART": "in_progress", "PAGE": "done",
    }

