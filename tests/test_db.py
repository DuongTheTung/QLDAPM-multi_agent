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


def test_project_agents_include_five_core_and_manage_custom_agent(tmp_path: Path):
    database = Database(tmp_path / "agents.db")
    database.init()
    database.create_project("project-1", "Test", "A sufficiently detailed comic prompt")

    agents = database.list_project_agents("project-1")
    assert len(agents) == 5
    assert all(agent["is_core"] for agent in agents)

    custom = database.create_project_agent(
        "project-1", "An Toàn", "Cố vấn an toàn", "Kiểm tra nội dung phù hợp trẻ em.", "#557a68"
    )
    assert len(database.list_project_agents("project-1")) == 6
    assert database.update_project_agent("project-1", custom["id"], enabled=False)
    assert database.get_project_agent("project-1", custom["id"])["enabled"] is False
    assert database.delete_project_agent("project-1", custom["id"])
    assert len(database.list_project_agents("project-1")) == 5

