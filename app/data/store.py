"""Persistent application store for users, sessions, research history, templates and citations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.settings import get_settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _database_path() -> Path:
    path = get_settings().app_database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'admin')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS research_sessions (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS research_tasks (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(thread_id) REFERENCES research_sessions(thread_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(thread_id) REFERENCES research_sessions(thread_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_task_events_thread ON task_events(thread_id, id);
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(thread_id, url),
    FOREIGN KEY(thread_id) REFERENCES research_sessions(thread_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS research_templates (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    prompt TEXT NOT NULL,
    category TEXT NOT NULL,
    created_by TEXT,
    is_public INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
);
"""

DEFAULT_TEMPLATES = [
    (
        "template-market-scan",
        "市场与竞品扫描",
        "输出市场规模、竞争格局、关键玩家和机会判断。",
        "请围绕【研究主题】开展市场与竞品扫描：先给出研究范围和口径，再分析市场趋势、主要玩家、产品差异、增长信号与潜在风险；事实必须附来源，最后输出机会优先级和下一步验证清单。",
        "市场研究",
    ),
    (
        "template-company-due-diligence",
        "企业尽调简报",
        "面向合作、投资或采购场景的企业背景调查。",
        "请对【企业名称】进行公开信息尽调，覆盖公司概况、核心产品、管理团队、融资与经营信号、主要客户或合作、舆情与合规风险。区分已证实事实和分析推断，并附来源及信息日期。",
        "企业研究",
    ),
    (
        "template-data-insight",
        "结构化数据洞察",
        "自动发现数据表并形成指标、异常和行动建议。",
        "请使用数据库工具先发现可用表和字段，再围绕【分析目标】执行只读分析。输出关键指标、趋势、异常点、数据限制和可执行建议，并说明每个结论使用的字段和筛选条件。",
        "数据分析",
    ),
    (
        "template-document-review",
        "文档审阅与风险清单",
        "对上传材料进行摘要、证据定位和风险审阅。",
        "请读取本会话上传的文件，形成执行摘要、核心事实、关键数字、矛盾或缺口、风险清单以及待确认问题。引用具体文件名和对应内容位置，不要补造材料中不存在的信息。",
        "文档分析",
    ),
]


def initialize_app_database() -> Path:
    with closing(_connect()) as connection:
        connection.executescript(SCHEMA)
        now = utc_now()
        for template_id, title, description, prompt, category in DEFAULT_TEMPLATES:
            connection.execute(
                """INSERT OR IGNORE INTO research_templates
                (id, title, description, prompt, category, created_by, is_public, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?)""",
                (template_id, title, description, prompt, category, now, now),
            )
        connection.commit()
    return _database_path()


def create_user(email: str, display_name: str, password_hash: str, role: str = "member") -> dict[str, Any]:
    now = utc_now()
    user_id = str(uuid.uuid4())
    with closing(_connect()) as connection:
        try:
            connection.execute(
                "INSERT INTO users (id, email, display_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email.strip().lower(), display_name.strip(), password_hash, role, now),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("该邮箱已注册") from exc
    return get_user_by_id(user_id) or {}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def mark_login(user_id: str) -> None:
    with closing(_connect()) as connection:
        connection.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user_id))
        connection.commit()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: user.get(key) for key in ("id", "email", "display_name", "role", "active", "created_at", "last_login_at")}


def claim_session(thread_id: str, user_id: str) -> None:
    now = utc_now()
    with closing(_connect()) as connection:
        row = connection.execute("SELECT user_id FROM research_sessions WHERE thread_id = ?", (thread_id,)).fetchone()
        if row and row["user_id"] != user_id:
            raise PermissionError("该会话属于其他用户")
        connection.execute(
            """INSERT INTO research_sessions (thread_id, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at""",
            (thread_id, user_id, now, now),
        )
        connection.commit()


def user_owns_thread(thread_id: str, user_id: str) -> bool:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT 1 FROM research_sessions WHERE thread_id = ? AND user_id = ?",
            (thread_id, user_id),
        ).fetchone()
    return bool(row)


def create_or_restart_task(thread_id: str, user_id: str, query: str) -> dict[str, Any]:
    claim_session(thread_id, user_id)
    now = utc_now()
    task_id = str(uuid.uuid4())
    with closing(_connect()) as connection:
        connection.execute(
            """INSERT INTO research_tasks
            (id, thread_id, user_id, query, status, result, error, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, 'running', '', '', ?, ?, NULL)
            ON CONFLICT(thread_id) DO UPDATE SET
              query = excluded.query, status = 'running', result = '', error = '',
              updated_at = excluded.updated_at, completed_at = NULL""",
            (task_id, thread_id, user_id, query, now, now),
        )
        connection.execute("DELETE FROM task_events WHERE thread_id = ?", (thread_id,))
        connection.execute("DELETE FROM citations WHERE thread_id = ?", (thread_id,))
        connection.commit()
    return get_task(thread_id, user_id) or {}


def add_task_event(thread_id: str, event_type: str, message: str, data: dict[str, Any], timestamp: str) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO task_events (thread_id, event_type, message, data_json, timestamp) VALUES (?, ?, ?, ?, ?)",
            (thread_id, event_type, message, json.dumps(data, ensure_ascii=False, default=str), timestamp),
        )
        connection.execute("UPDATE research_sessions SET updated_at = ? WHERE thread_id = ?", (timestamp, thread_id))
        connection.commit()


def update_task_status(thread_id: str, status: str, result: str = "", error: str = "") -> None:
    now = utc_now()
    completed_at = now if status in {"completed", "failed", "cancelled"} else None
    with closing(_connect()) as connection:
        connection.execute(
            """UPDATE research_tasks SET status = ?, result = ?, error = ?, updated_at = ?, completed_at = ?
            WHERE thread_id = ?""",
            (status, result, error, now, completed_at, thread_id),
        )
        connection.commit()


def add_citations(thread_id: str, sources: list[dict[str, Any]]) -> None:
    now = utc_now()
    with closing(_connect()) as connection:
        for source in sources:
            url = str(source.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            title = str(source.get("title") or url).strip()[:500]
            snippet = str(source.get("snippet") or source.get("content") or "").strip()[:2000]
            domain = urlparse(url).netloc.lower()
            connection.execute(
                """INSERT INTO citations (thread_id, title, url, domain, snippet, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id, url) DO UPDATE SET title = excluded.title, snippet = excluded.snippet""",
                (thread_id, title, url, domain, snippet, now),
            )
        connection.commit()


def _task_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def list_tasks(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """SELECT t.*, (SELECT COUNT(*) FROM citations c WHERE c.thread_id=t.thread_id) AS citation_count,
            (SELECT COUNT(*) FROM task_events e WHERE e.thread_id=t.thread_id) AS event_count
            FROM research_tasks t WHERE t.user_id = ? ORDER BY t.updated_at DESC LIMIT ?""",
            (user_id, min(max(limit, 1), 200)),
        ).fetchall()
    return [_task_row(row) for row in rows]


def get_task(thread_id: str, user_id: str | None = None, admin: bool = False) -> dict[str, Any] | None:
    query = "SELECT * FROM research_tasks WHERE thread_id = ?"
    params: tuple[Any, ...] = (thread_id,)
    if user_id and not admin:
        query += " AND user_id = ?"
        params = (thread_id, user_id)
    with closing(_connect()) as connection:
        row = connection.execute(query, params).fetchone()
        if not row:
            return None
        task = dict(row)
        event_rows = connection.execute(
            "SELECT event_type, message, data_json, timestamp FROM task_events WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
        citation_rows = connection.execute(
            "SELECT id, title, url, domain, snippet, created_at FROM citations WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
    task["events"] = [
        {
            "type": "monitor_event",
            "event": event["event_type"],
            "message": event["message"],
            "data": json.loads(event["data_json"]),
            "timestamp": event["timestamp"],
        }
        for event in event_rows
    ]
    task["citations"] = [dict(row) for row in citation_rows]
    return task


def delete_task(thread_id: str, user_id: str, admin: bool = False) -> bool:
    with closing(_connect()) as connection:
        if admin:
            cursor = connection.execute("DELETE FROM research_sessions WHERE thread_id = ?", (thread_id,))
        else:
            cursor = connection.execute(
                "DELETE FROM research_sessions WHERE thread_id = ? AND user_id = ?", (thread_id, user_id)
            )
        connection.commit()
    return cursor.rowcount > 0


def list_templates(user_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """SELECT * FROM research_templates
            WHERE is_public = 1 OR created_by = ? ORDER BY category, updated_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_template(user_id: str, payload: dict[str, Any], is_admin: bool = False) -> dict[str, Any]:
    now = utc_now()
    template_id = str(uuid.uuid4())
    is_public = 1 if is_admin and payload.get("is_public") else 0
    with closing(_connect()) as connection:
        connection.execute(
            """INSERT INTO research_templates
            (id, title, description, prompt, category, created_by, is_public, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (template_id, payload["title"], payload["description"], payload["prompt"], payload["category"], user_id, is_public, now, now),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM research_templates WHERE id = ?", (template_id,)).fetchone()
    return dict(row)


def delete_template(template_id: str, user_id: str, is_admin: bool = False) -> bool:
    with closing(_connect()) as connection:
        if is_admin:
            cursor = connection.execute("DELETE FROM research_templates WHERE id = ?", (template_id,))
        else:
            cursor = connection.execute(
                "DELETE FROM research_templates WHERE id = ? AND created_by = ?", (template_id, user_id)
            )
        connection.commit()
    return cursor.rowcount > 0


def list_users() -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """SELECT u.id, u.email, u.display_name, u.role, u.active, u.created_at, u.last_login_at,
            COUNT(t.id) AS task_count FROM users u LEFT JOIN research_tasks t ON t.user_id=u.id
            GROUP BY u.id ORDER BY u.created_at DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


def admin_stats() -> dict[str, Any]:
    with closing(_connect()) as connection:
        users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        tasks = connection.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0]
        completed = connection.execute("SELECT COUNT(*) FROM research_tasks WHERE status='completed'").fetchone()[0]
        citations = connection.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
        recent = connection.execute(
            """SELECT t.thread_id, t.query, t.status, t.updated_at, u.display_name, u.email
            FROM research_tasks t JOIN users u ON u.id=t.user_id ORDER BY t.updated_at DESC LIMIT 20"""
        ).fetchall()
    return {
        "users": users,
        "tasks": tasks,
        "completed_tasks": completed,
        "citations": citations,
        "recent_tasks": [dict(row) for row in recent],
    }
