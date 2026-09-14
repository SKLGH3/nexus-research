"""Create the zero-configuration SQLite demonstration database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT NOT NULL,
    region TEXT NOT NULL,
    founded_year INTEGER NOT NULL,
    employee_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS market_signals (
    signal_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    signal_type TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    score REAL NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);
CREATE TABLE IF NOT EXISTS research_projects (
    project_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    budget REAL NOT NULL,
    due_date TEXT NOT NULL
);
"""

COMPANIES = [
    (1, "远澜机器人", "具身智能", "上海", 2019, 680),
    (2, "云图智算", "企业AI", "北京", 2017, 1250),
    (3, "澄海能源", "新能源", "深圳", 2015, 2100),
    (4, "星桥零售", "跨境电商", "杭州", 2020, 940),
    (5, "矩阵生物", "生命科学", "苏州", 2018, 520),
]

SIGNALS = [
    (1, 1, "产品", "2026-08-18", 92, "发布新一代工业具身机器人平台", "企业公告"),
    (2, 1, "融资", "2026-07-05", 86, "完成新一轮战略融资并扩建交付中心", "公开新闻"),
    (3, 2, "合作", "2026-08-26", 89, "与区域制造集团签署AI平台合作", "行业媒体"),
    (4, 3, "政策", "2026-06-21", 74, "所在园区发布储能项目支持政策", "政府网站"),
    (5, 4, "增长", "2026-09-01", 95, "海外订单同比增长并进入两个新市场", "经营简报"),
    (6, 5, "研发", "2026-07-30", 83, "完成多组学分析产品内部验证", "企业公告"),
]

PROJECTS = [
    (1, "具身智能行业机会扫描", "战略研究组", "active", "P0", 180000, "2026-10-15"),
    (2, "跨境电商AI客服竞品研究", "产品洞察组", "active", "P1", 95000, "2026-09-30"),
    (3, "新能源政策知识库建设", "数据平台组", "planning", "P1", 130000, "2026-11-20"),
    (4, "生命科学投研信号模型", "行业研究组", "review", "P2", 76000, "2026-10-08"),
]


def ensure_demo_database(database_path: Path) -> Path:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(SCHEMA)
        if connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?)", COMPANIES
            )
            connection.executemany(
                "INSERT INTO market_signals VALUES (?, ?, ?, ?, ?, ?, ?)", SIGNALS
            )
            connection.executemany(
                "INSERT INTO research_projects VALUES (?, ?, ?, ?, ?, ?, ?)", PROJECTS
            )
        connection.commit()
    return database_path

