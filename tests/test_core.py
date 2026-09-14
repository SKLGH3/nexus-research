from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.server import _safe_thread_id, _session_file, app
from app.data.bootstrap import ensure_demo_database
from app.api.auth import hash_password, verify_password
from app.data.store import add_citations, add_task_event, create_or_restart_task, create_user, get_task, initialize_app_database, update_task_status
from app.tools.db_tools import _validate_read_only_query, _validate_table_name


class DatabaseSafetyTests(unittest.TestCase):
    def test_read_only_query_allows_select_and_cte(self) -> None:
        self.assertEqual(_validate_read_only_query("SELECT 1;"), "SELECT 1")
        self.assertEqual(
            _validate_read_only_query("WITH sample AS (SELECT 1 AS value) SELECT value FROM sample"),
            "WITH sample AS (SELECT 1 AS value) SELECT value FROM sample",
        )

    def test_read_only_query_rejects_mutation_and_multiple_statements(self) -> None:
        for query in (
            "DELETE FROM companies",
            "SELECT 1; DROP TABLE companies",
            "WITH changed AS (DELETE FROM companies RETURNING *) SELECT * FROM changed",
            "SELECT 1 -- hidden statement",
        ):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    _validate_read_only_query(query)

    def test_table_name_rejects_injection(self) -> None:
        self.assertEqual(_validate_table_name("market_signals"), "market_signals")
        for name in ("market_signals;DROP", "../companies", "1table", "company-name"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    _validate_table_name(name)

    def test_demo_database_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = ensure_demo_database(Path(temp_dir) / "demo.db")
            with closing(sqlite3.connect(database_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                company_count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            self.assertTrue({"companies", "market_signals", "research_projects"}.issubset(tables))
            self.assertGreater(company_count, 0)


class ApiSafetyTests(unittest.TestCase):
    def test_thread_id_validation(self) -> None:
        self.assertEqual(_safe_thread_id("case_2026-09"), "case_2026-09")
        for value in ("../escape", "bad id", "x" * 65):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    _safe_thread_id(value)

    def test_session_file_rejects_traversal(self) -> None:
        with self.assertRaises(HTTPException):
            _session_file("safe-thread", "../outside.txt")

    def test_health_and_public_config(self) -> None:
        with TestClient(app) as client:
            health = client.get("/api/health")
            config = client.get("/api/config")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(config.status_code, 200)
        self.assertIn("model", config.json())
        self.assertNotIn("api_key", config.json()["model"])


class AuthenticationAndHistoryTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        encoded = hash_password("secure-password")
        self.assertTrue(verify_password("secure-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_registration_permissions_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.data.store._database_path", return_value=Path(temp_dir) / "app.db"
        ):
            initialize_app_database()
            suffix = uuid.uuid4().hex
            email = f"member-{suffix}@example.com"
            thread_id = f"case-{suffix[:16]}"
            with TestClient(app) as client:
                unauthorized = client.get("/api/history")
                self.assertEqual(unauthorized.status_code, 401)
                registered = client.post(
                    "/api/auth/register",
                    json={"email": email, "display_name": "Test Member", "password": "password-123"},
                )
                self.assertEqual(registered.status_code, 200)
                token = registered.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                self.assertEqual(client.get("/api/auth/me", headers=headers).status_code, 200)
                self.assertEqual(client.get("/api/admin/overview", headers=headers).status_code, 403)

                user_id = registered.json()["user"]["id"]
                create_or_restart_task(thread_id, user_id, "测试持久化研究")
                add_task_event(thread_id, "tool_start", "开始测试", {"tool": "test"}, "2026-09-14T00:00:00+00:00")
                sources = [{"title": "Example", "url": "https://example.com/report", "snippet": "evidence"}]
                add_citations(thread_id, sources)
                add_citations(thread_id, sources)
                update_task_status(thread_id, "completed", result="done")

                detail = client.get(f"/api/history/{thread_id}", headers=headers)
                self.assertEqual(detail.status_code, 200)
                payload = detail.json()
                self.assertEqual(payload["result"], "done")
                self.assertEqual(len(payload["events"]), 1)
                self.assertEqual(len(payload["citations"]), 1)

                other = create_user(f"other-{suffix}@example.com", "Other", hash_password("password-123"))
                self.assertIsNone(get_task(thread_id, other["id"]))


if __name__ == "__main__":
    unittest.main()
