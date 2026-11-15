from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .schemas import utcnow

CORE_AGENT_SEEDS = (
    ("pm", "Tùng", "PM", "Quản lý kế hoạch, lịch, tiến độ và điều phối xử lý lỗi.", "#263f35"),
    ("writer", "Sơn", "Biên kịch", "Viết cấu trúc truyện, phân trang và đoạn kể phù hợp lứa tuổi.", "#dd5c3d"),
    ("designer", "Hải", "Thiết kế nhân vật", "Khóa phong cách, nhân vật, bối cảnh và tạo ảnh tham chiếu.", "#d99b2b"),
    ("artist", "Sáng", "Họa sĩ", "Tạo prompt và minh họa bìa, từng trang theo kịch bản đã khóa.", "#426b91"),
    ("reviewer", "Minh", "Kiểm duyệt", "Kiểm tra từng đầu ra ngay khi hoàn thành và trả lỗi về đúng agent.", "#3f8178"),
    ("editor", "Trí", "Biên tập & dàn trang", "Ghép tranh với khối văn bản riêng, hoàn thiện bìa và xuất PDF.", "#7d5c8d"),
)


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        with self._lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    final_pdf TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    depends_on TEXT NOT NULL DEFAULT '[]',
                    detail TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0,
                    parent_id TEXT,
                    item_type TEXT NOT NULL DEFAULT 'task',
                    step_key TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS project_agents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    color TEXT NOT NULL,
                    is_core INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    content_json TEXT NOT NULL DEFAULT '{}',
                    event_id INTEGER,
                    feedback TEXT NOT NULL DEFAULT '',
                    assigned_agent TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(event_id) REFERENCES events(id)
                );
                CREATE TABLE IF NOT EXISTS interventions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    event_id INTEGER,
                    action TEXT NOT NULL,
                    target_agent TEXT,
                    content_key TEXT,
                    feedback TEXT NOT NULL DEFAULT '',
                    before_json TEXT,
                    after_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quality_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    owner_agent TEXT NOT NULL,
                    reviewer_agent TEXT NOT NULL DEFAULT 'reviewer',
                    unit_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'testing',
                    verdict TEXT,
                    feedback TEXT NOT NULL DEFAULT '',
                    artifact_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_project_agents_project ON project_agents(project_id, is_core, created_at);
                CREATE INDEX IF NOT EXISTS idx_approvals_project ON approvals(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_interventions_project ON interventions(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_quality_tests_project ON quality_tests(project_id, id);
                """
            )
            self._ensure_column(db, "projects", "pause_requested", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, "projects", "approval_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(
                db, "projects", "approval_stages",
                "TEXT NOT NULL DEFAULT '[\"script\",\"character_design\",\"illustration\",\"final\"]'",
            )
            self._ensure_column(db, "project_agents", "model", "TEXT")
            self._ensure_column(db, "project_agents", "fallback_models", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "project_agents", "image_model", "TEXT")
            self._ensure_column(db, "project_agents", "temperature", "REAL")
            self._ensure_column(db, "tasks", "parent_id", "TEXT")
            self._ensure_column(db, "tasks", "item_type", "TEXT NOT NULL DEFAULT 'task'")
            self._ensure_column(db, "tasks", "step_key", "TEXT NOT NULL DEFAULT ''")
            for row in db.execute("SELECT id FROM projects"):
                self._insert_core_agents(db, row["id"])

    def get_app_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute(
                "SELECT value_json FROM app_settings WHERE key=?", (key,),
            ).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set_app_setting(self, key: str, value: Any) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), utcnow()),
            )

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, definition: str,
    ) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _insert_core_agents(db: sqlite3.Connection, project_id: str) -> None:
        now = utcnow()
        for agent_id, name, role, instructions, color in CORE_AGENT_SEEDS:
            db.execute(
                "INSERT OR IGNORE INTO project_agents "
                "(id,project_id,name,role,instructions,color,is_core,enabled,created_at) "
                "VALUES(?,?,?,?,?,?,1,1,?)",
                (f"{project_id}:{agent_id}", project_id, name, role, instructions, color, now),
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        item = dict(row)
        if "pause_requested" in item:
            item["pause_requested"] = bool(item["pause_requested"])
        if "approval_enabled" in item:
            item["approval_enabled"] = bool(item["approval_enabled"])
        if "approval_stages" in item:
            item["approval_stages"] = json.loads(item["approval_stages"] or "[]")
        return item

    def create_project(self, project_id: str, title: str, prompt: str) -> dict[str, Any]:
        now = utcnow()
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO projects(id,title,prompt,status,stage,progress,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (project_id, title, prompt, "queued", "brief", 0, now, now),
            )
            self._insert_core_agents(db, project_id)
        return self.get_project(project_id)  # type: ignore[return-value]

    @staticmethod
    def _agent_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["is_core"] = bool(item["is_core"])
        item["enabled"] = bool(item["enabled"])
        item["key"] = item["id"].split(":", 1)[1] if item["is_core"] else item["id"]
        item["fallback_models"] = json.loads(item.get("fallback_models") or "[]")
        return item

    def list_project_agents(
        self, project_id: str, *, custom_only: bool = False, enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["project_id=?"]
        values: list[Any] = [project_id]
        if custom_only:
            clauses.append("is_core=0")
        if enabled_only:
            clauses.append("enabled=1")
        query = (
            "SELECT * FROM project_agents WHERE " + " AND ".join(clauses)
            + " ORDER BY is_core DESC, created_at, name"
        )
        with self.connect() as db:
            return [self._agent_row(row) for row in db.execute(query, values)]

    def get_project_agent(self, project_id: str, agent_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM project_agents WHERE project_id=? AND id=?",
                (project_id, agent_id),
            ).fetchone()
        return self._agent_row(row) if row else None

    def create_project_agent(
        self, project_id: str, name: str, role: str, instructions: str, color: str,
        model: str | None = None, fallback_models: list[str] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        import uuid

        agent_id = f"custom-{uuid.uuid4().hex[:10]}"
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO project_agents "
                "(id,project_id,name,role,instructions,color,is_core,enabled,created_at,"
                "model,fallback_models,temperature) VALUES(?,?,?,?,?,?,0,1,?,?,?,?)",
                (
                    agent_id, project_id, name, role, instructions, color, utcnow(), model,
                    json.dumps(fallback_models or []), temperature,
                ),
            )
        return self.get_project_agent(project_id, agent_id)  # type: ignore[return-value]

    def update_project_agent(self, project_id: str, agent_id: str, **fields: Any) -> bool:
        allowed = {
            "name", "role", "instructions", "color", "enabled", "model",
            "fallback_models", "image_model", "temperature",
        }
        nullable_config = {"model", "fallback_models", "image_model", "temperature"}
        selected = {
            key: value for key, value in fields.items()
            if key in allowed and (value is not None or key in nullable_config)
        }
        if not selected:
            return bool(self.get_project_agent(project_id, agent_id))
        if "enabled" in selected:
            selected["enabled"] = int(bool(selected["enabled"]))
        if "fallback_models" in selected:
            selected["fallback_models"] = json.dumps(selected["fallback_models"] or [])
        assignments = ",".join(f"{key}=?" for key in selected)
        with self._lock, self.connect() as db:
            cursor = db.execute(
                f"UPDATE project_agents SET {assignments} WHERE project_id=? AND id=?",
                [*selected.values(), project_id, agent_id],
            )
            return cursor.rowcount > 0

    def delete_project_agent(self, project_id: str, agent_id: str) -> bool:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "DELETE FROM project_agents WHERE project_id=? AND id=? AND is_core=0",
                (project_id, agent_id),
            )
            return cursor.rowcount > 0

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [self._row(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at DESC")]  # type: ignore[misc]

    def update_project(self, project_id: str, **fields: Any) -> None:
        allowed = {
            "title", "status", "stage", "progress", "state_json", "final_pdf", "error",
            "pause_requested", "approval_enabled", "approval_stages",
        }
        selected = {key: value for key, value in fields.items() if key in allowed}
        if not selected:
            return
        if "pause_requested" in selected:
            selected["pause_requested"] = int(bool(selected["pause_requested"]))
        if "approval_enabled" in selected:
            selected["approval_enabled"] = int(bool(selected["approval_enabled"]))
        if "approval_stages" in selected:
            selected["approval_stages"] = json.dumps(selected["approval_stages"])
        selected["updated_at"] = utcnow()
        assignments = ",".join(f"{key}=?" for key in selected)
        with self._lock, self.connect() as db:
            db.execute(
                f"UPDATE projects SET {assignments} WHERE id=?",
                [*selected.values(), project_id],
            )

    def replace_tasks(self, project_id: str, tasks: list[dict[str, Any]]) -> None:
        with self._lock, self.connect() as db:
            db.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
            for index, task in enumerate(tasks):
                db.execute(
                    "INSERT INTO tasks(id,project_id,title,agent,status,start_at,due_at,"
                    "depends_on,detail,order_index,parent_id,item_type,step_key) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        task["id"], project_id, task["title"], task["agent"], task["status"],
                        task["start_at"], task["due_at"], json.dumps(task.get("depends_on", [])),
                        task.get("detail", ""), task.get("order_index", index),
                        task.get("parent_id"), task.get("item_type", "task"),
                        task.get("step_key", ""),
                    ),
                )

    def get_tasks(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY order_index", (project_id,)
            )]
        for row in rows:
            row["depends_on"] = json.loads(row["depends_on"])
        return rows

    def set_task_status(self, project_id: str, agent: str, status: str, detail: str = "") -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE tasks SET status=?, detail=CASE WHEN ?='' THEN detail ELSE ? END "
                "WHERE project_id=? AND agent=?",
                (status, detail, detail, project_id, agent),
            )

    def start_agent_work(self, project_id: str, agent: str) -> None:
        with self._lock, self.connect() as db:
            parent = db.execute(
                "SELECT id FROM tasks WHERE project_id=? AND agent=? AND item_type='task' "
                "AND status!='done' ORDER BY order_index LIMIT 1",
                (project_id, agent),
            ).fetchone()
            if parent:
                db.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (parent["id"],))
                child = db.execute(
                    "SELECT id FROM tasks WHERE project_id=? AND parent_id=? AND status='todo' "
                    "ORDER BY order_index LIMIT 1",
                    (project_id, parent["id"]),
                ).fetchone()
                if child:
                    db.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (child["id"],))

    def set_task_step(self, project_id: str, agent: str, step_key: str) -> None:
        with self._lock, self.connect() as db:
            current = db.execute(
                "SELECT id,parent_id FROM tasks WHERE project_id=? AND agent=? AND step_key=? "
                "ORDER BY order_index LIMIT 1",
                (project_id, agent, step_key),
            ).fetchone()
            if not current:
                return
            db.execute(
                "UPDATE tasks SET status='done' WHERE project_id=? AND agent=? "
                "AND item_type='subtask' AND status='in_progress' AND id!=?",
                (project_id, agent, current["id"]),
            )
            db.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (current["id"],))
            if current["parent_id"]:
                db.execute(
                    "UPDATE tasks SET status='in_progress' WHERE id=? AND status!='done'",
                    (current["parent_id"],),
                )

    def complete_agent_work(self, project_id: str, agent: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE tasks SET status='done' WHERE project_id=? AND agent=? "
                "AND status IN ('todo','in_progress')",
                (project_id, agent),
            )

    def begin_task_testing(self, project_id: str, agent: str, step_key: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE tasks SET status='testing' WHERE project_id=? AND agent=? "
                "AND step_key=?",
                (project_id, agent, step_key),
            )
            db.execute(
                "UPDATE tasks SET status='testing' WHERE project_id=? AND agent=? "
                "AND item_type='task' AND status!='done'",
                (project_id, agent),
            )

    def finish_task_testing(
        self, project_id: str, agent: str, step_key: str, passed: bool,
    ) -> None:
        status = "done" if passed else "in_progress"
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE tasks SET status=? WHERE project_id=? AND agent=? AND step_key=?",
                (status, project_id, agent, step_key),
            )
            db.execute(
                "UPDATE tasks SET status='in_progress' WHERE project_id=? AND agent=? "
                "AND item_type='task' AND status='testing'",
                (project_id, agent),
            )

    def create_quality_test(
        self, project_id: str, owner_agent: str, unit_key: str, title: str,
        artifact_ids: list[int] | None = None,
    ) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO quality_tests(project_id,owner_agent,unit_key,title,artifact_ids,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    project_id, owner_agent, unit_key, title,
                    json.dumps(artifact_ids or []), utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def finish_quality_test(
        self, test_id: int, verdict: str, feedback: str = "",
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE quality_tests SET status='completed',verdict=?,feedback=?,resolved_at=? "
                "WHERE id=?",
                (verdict, feedback, utcnow(), test_id),
            )

    def list_quality_tests(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM quality_tests WHERE project_id=? ORDER BY id", (project_id,)
            )]
        for row in rows:
            row["artifact_ids"] = json.loads(row["artifact_ids"] or "[]")
        return rows

    def add_revision_task(self, project_id: str, agent: str, title: str, detail: str, order: int) -> None:
        import uuid
        now = utcnow()
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO tasks(id,project_id,title,agent,status,start_at,due_at,"
                "depends_on,detail,order_index,parent_id,item_type,step_key) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"REV-{uuid.uuid4().hex[:7]}", project_id, title, agent, "in_progress", now, now,
                 "[]", detail, order, None, "task", "revision"),
            )

    def add_event(
        self, project_id: str, agent: str, event_type: str, message: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO events(project_id,agent,event_type,message,payload,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (project_id, agent, event_type, message, json.dumps(payload or {}, ensure_ascii=False), utcnow()),
            )
            return int(cursor.lastrowid)

    def get_events(self, project_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM events WHERE project_id=? AND id>? ORDER BY id", (project_id, after)
            )]
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def get_event(self, project_id: str, event_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM events WHERE project_id=? AND id=?", (project_id, event_id)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    def create_approval(
        self, project_id: str, stage: str, signature: str, content: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO approvals(project_id,stage,signature,content_json,created_at) "
                "VALUES(?,?,?,?,?)",
                (project_id, stage, signature, json.dumps(content, ensure_ascii=False), utcnow()),
            )
            approval_id = int(cursor.lastrowid)
        return self.get_approval(project_id, approval_id)  # type: ignore[return-value]

    @staticmethod
    def _approval_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["content"] = json.loads(item.pop("content_json") or "{}")
        return item

    def get_approval(self, project_id: str, approval_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM approvals WHERE project_id=? AND id=?",
                (project_id, approval_id),
            ).fetchone()
        return self._approval_row(row) if row else None

    def get_approval_by_signature(
        self, project_id: str, signature: str,
    ) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM approvals WHERE project_id=? AND signature=? ORDER BY id DESC LIMIT 1",
                (project_id, signature),
            ).fetchone()
        return self._approval_row(row) if row else None

    def list_approvals(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [self._approval_row(row) for row in db.execute(
                "SELECT * FROM approvals WHERE project_id=? ORDER BY id", (project_id,)
            )]

    def link_approval_event(self, project_id: str, approval_id: int, event_id: int) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE approvals SET event_id=? WHERE project_id=? AND id=?",
                (event_id, project_id, approval_id),
            )

    def resolve_approval(
        self, project_id: str, approval_id: int, status: str, feedback: str = "",
        assigned_agent: str | None = None,
    ) -> bool:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "UPDATE approvals SET status=?,feedback=?,assigned_agent=?,resolved_at=? "
                "WHERE project_id=? AND id=? AND status='pending'",
                (status, feedback, assigned_agent, utcnow(), project_id, approval_id),
            )
            return cursor.rowcount > 0

    def add_intervention(
        self, project_id: str, action: str, *, event_id: int | None = None,
        target_agent: str | None = None, content_key: str | None = None,
        feedback: str = "", before: Any = None, after: Any = None,
    ) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO interventions(project_id,event_id,action,target_agent,content_key,feedback,"
                "before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    project_id, event_id, action, target_agent, content_key, feedback,
                    json.dumps(before, ensure_ascii=False) if before is not None else None,
                    json.dumps(after, ensure_ascii=False) if after is not None else None,
                    utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def list_interventions(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM interventions WHERE project_id=? ORDER BY id", (project_id,)
            )]
        for row in rows:
            row["before"] = json.loads(row.pop("before_json")) if row["before_json"] else None
            row["after"] = json.loads(row.pop("after_json")) if row["after_json"] else None
        return rows

    def add_artifact(self, project_id: str, agent: str, kind: str, name: str, path: str) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO artifacts(project_id,agent,kind,name,path,created_at) VALUES(?,?,?,?,?,?)",
                (project_id, agent, kind, name, path, utcnow()),
            )
            return int(cursor.lastrowid)

    def get_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM artifacts WHERE project_id=? ORDER BY id DESC", (project_id,)
            )]

    def delete_project(self, project_id: str) -> bool:
        """Delete one project and its relational records as a single transaction."""
        with self._lock, self.connect() as db:
            exists = db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
            if not exists:
                return False
            for table in (
                "interventions", "approvals", "quality_tests", "events", "tasks", "artifacts", "project_agents",
            ):
                db.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            return True

