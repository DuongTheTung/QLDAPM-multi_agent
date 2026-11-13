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
    ("writer", "Sơn", "Biên kịch", "Viết cấu trúc truyện, phân trang và lời thoại phù hợp lứa tuổi.", "#dd5c3d"),
    ("designer", "Hải", "Thiết kế nhân vật", "Khóa phong cách, nhân vật, bối cảnh và tạo ảnh tham chiếu.", "#d99b2b"),
    ("artist", "Sáng", "Họa sĩ", "Tạo prompt và minh họa bìa, từng trang theo kịch bản đã khóa.", "#426b91"),
    ("editor", "Trí", "Biên tập & dàn trang", "Duyệt chất lượng, gắn bóng thoại và hoàn thiện PDF.", "#7d5c8d"),
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
                CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id, id);
                CREATE INDEX IF NOT EXISTS idx_project_agents_project ON project_agents(project_id, is_core, created_at);
                """
            )
            for row in db.execute("SELECT id FROM projects"):
                self._insert_core_agents(db, row["id"])

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
        return dict(row) if row else None

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
    ) -> dict[str, Any]:
        import uuid

        agent_id = f"custom-{uuid.uuid4().hex[:10]}"
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO project_agents "
                "(id,project_id,name,role,instructions,color,is_core,enabled,created_at) "
                "VALUES(?,?,?,?,?,?,0,1,?)",
                (agent_id, project_id, name, role, instructions, color, utcnow()),
            )
        return self.get_project_agent(project_id, agent_id)  # type: ignore[return-value]

    def update_project_agent(self, project_id: str, agent_id: str, **fields: Any) -> bool:
        allowed = {"name", "role", "instructions", "color", "enabled"}
        selected = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not selected:
            return bool(self.get_project_agent(project_id, agent_id))
        if "enabled" in selected:
            selected["enabled"] = int(bool(selected["enabled"]))
        assignments = ",".join(f"{key}=?" for key in selected)
        with self._lock, self.connect() as db:
            cursor = db.execute(
                f"UPDATE project_agents SET {assignments} WHERE project_id=? AND id=? AND is_core=0",
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
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at DESC")]

    def update_project(self, project_id: str, **fields: Any) -> None:
        allowed = {"title", "status", "stage", "progress", "state_json", "final_pdf", "error"}
        selected = {key: value for key, value in fields.items() if key in allowed}
        if not selected:
            return
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
                    "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        task["id"], project_id, task["title"], task["agent"], task["status"],
                        task["start_at"], task["due_at"], json.dumps(task.get("depends_on", [])),
                        task.get("detail", ""), task.get("order_index", index),
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

    def add_revision_task(self, project_id: str, agent: str, title: str, detail: str, order: int) -> None:
        import uuid
        now = utcnow()
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)",
                (f"REV-{uuid.uuid4().hex[:7]}", project_id, title, agent, "in_progress", now, now,
                 "[]", detail, order),
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

    def add_artifact(self, project_id: str, agent: str, kind: str, name: str, path: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO artifacts(project_id,agent,kind,name,path,created_at) VALUES(?,?,?,?,?,?)",
                (project_id, agent, kind, name, path, utcnow()),
            )

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
            for table in ("events", "tasks", "artifacts", "project_agents"):
                db.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            return True

