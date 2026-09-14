"""Read-only database tools with SQLite and MySQL adapters."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from langchain_core.tools import tool
from mysql.connector import connect as mysql_connect

from app.api.monitor import monitor
from app.core.settings import get_settings
from app.data.bootstrap import ensure_demo_database

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_READ_ONLY_START = re.compile(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.I)
_MUTATING_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|REPLACE|CREATE|GRANT|REVOKE|CALL|LOAD|ATTACH|DETACH|VACUUM|PRAGMA)\b",
    re.I,
)
MAX_ROWS = 200


def _driver() -> str:
    driver = get_settings().database_driver
    if driver not in {"sqlite", "mysql"}:
        raise ValueError("DATABASE_DRIVER 仅支持 sqlite 或 mysql")
    return driver


@contextmanager
def _connection() -> Iterator[Any]:
    settings = get_settings()
    if _driver() == "sqlite":
        database_path = ensure_demo_database(settings.sqlite_path)
        connection = sqlite3.connect(database_path)
        try:
            yield connection
        finally:
            connection.close()
        return

    connection = mysql_connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset=settings.mysql_charset,
        collation=settings.mysql_collation,
        autocommit=True,
        sql_mode=settings.mysql_sql_mode,
    )
    try:
        yield connection
    finally:
        connection.close()


def _rows_to_csv(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().strip()


def _validate_table_name(table_name: str) -> str:
    cleaned = table_name.strip()
    if not _IDENTIFIER.fullmatch(cleaned):
        raise ValueError("表名只能包含字母、数字和下划线，且不能以数字开头")
    return cleaned


def _validate_read_only_query(query: str) -> str:
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned or not _READ_ONLY_START.match(cleaned):
        raise ValueError("仅允许 SELECT、WITH、SHOW、DESCRIBE 或 EXPLAIN 查询")
    if ";" in cleaned:
        raise ValueError("一次只能执行一条 SQL")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned or "#" in cleaned:
        raise ValueError("查询中不允许 SQL 注释")
    without_literals = re.sub(r''''(?:''|[^'])*'|"(?:""|[^"])*"''', "", cleaned)
    if _MUTATING_WORDS.search(without_literals):
        raise ValueError("检测到写入或结构变更语句，数据库工具只允许只读查询")
    return cleaned


def database_status() -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {"driver": settings.database_driver, "ready": False, "detail": ""}
    try:
        with _connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        result.update(ready=True, detail="连接正常")
    except Exception as exc:
        result["detail"] = str(exc)
    return result


@tool
def list_sql_tables() -> str:
    """列出当前数据库中所有可查询的数据表。"""
    monitor.report_tool("数据库表名查询：list_sql_tables", {})
    try:
        with _connection() as connection:
            cursor = connection.cursor()
            if _driver() == "sqlite":
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            else:
                cursor.execute("SHOW TABLES")
            tables = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
        return "可用的表有：" + ", ".join(tables) if tables else "没有可用的数据表"
    except Exception as exc:
        return f"查询出现异常：{exc}"


@tool
def get_table_data(table_name: str) -> str:
    """读取指定数据表的字段和前 100 行样例数据。"""
    monitor.report_tool("数据库表预览：get_table_data", {"table_name": table_name})
    try:
        safe_name = _validate_table_name(table_name)
        quote = '"' if _driver() == "sqlite" else chr(96)
        with _connection() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {quote}{safe_name}{quote} LIMIT 100")
            columns = [item[0] for item in cursor.description or []]
            rows = cursor.fetchall()
            cursor.close()
        if not columns:
            return f"数据表 {safe_name} 暂无可读取字段。"
        return _rows_to_csv(columns, rows)
    except Exception as exc:
        return f"查询出现异常：{exc}"


@tool
def execute_sql_query(query: str) -> str:
    """执行一条只读 SQL，并以 CSV 返回最多 200 行结果。"""
    monitor.report_tool("只读 SQL 查询：execute_sql_query", {"query": query})
    try:
        safe_query = _validate_read_only_query(query)
        with _connection() as connection:
            cursor = connection.cursor()
            cursor.execute(safe_query)
            columns = [item[0] for item in cursor.description or []]
            rows = cursor.fetchmany(MAX_ROWS + 1)
            cursor.close()
        if not columns:
            return "查询没有返回结果集。"
        truncated = len(rows) > MAX_ROWS
        body = _rows_to_csv(columns, rows[:MAX_ROWS])
        if truncated:
            body += f"\n[结果已截断，仅展示前 {MAX_ROWS} 行]"
        return body
    except Exception as exc:
        return f"查询出现异常：{exc}"


if __name__ == "__main__":
    print(list_sql_tables.invoke({}))
