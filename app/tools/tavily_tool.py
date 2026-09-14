"""Tavily web-search tool with lazy credential validation."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.tools import tool
from tavily import TavilyClient

from app.api.monitor import monitor
from app.core.settings import get_settings


@lru_cache(maxsize=1)
def _client() -> TavilyClient:
    api_key = get_settings().tavily_api_key
    if not api_key:
        raise RuntimeError("未配置 TAVILY_API_KEY，网络搜索能力暂不可用。")
    return TavilyClient(api_key=api_key)


@tool
def internet_search(
    query: str,
    topic: Literal["news", "finance", "general"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
) -> str:
    """检索互联网公开信息，并返回标题、链接、摘要和相关度。"""
    safe_max_results = min(max(max_results, 1), 8)
    monitor.report_tool(
        "网络搜索：internet_search",
        {"query": query, "topic": topic, "max_results": safe_max_results},
    )
    try:
        response = _client().search(
            query=query,
            topic=topic,
            search_depth="advanced",
            max_results=safe_max_results,
            include_raw_content=include_raw_content,
        )
        results = response.get("results", []) if isinstance(response, dict) else []
        if not results:
            return "未检索到匹配的公开资料。"
        sources = [
            {
                "title": str(item.get("title") or "未命名来源"),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("content") or ""),
                "score": item.get("score"),
            }
            for item in results
        ]
        monitor.report_sources(sources)
        chunks = []
        for index, item in enumerate(results, start=1):
            chunks.append(
                "\n".join(
                    [
                        f"[{index}] {item.get('title', '未命名来源')}",
                        f"URL: {item.get('url', '')}",
                        f"相关度: {item.get('score', '')}",
                        f"摘要: {item.get('content', '')}",
                    ]
                )
            )
        return "\n\n".join(chunks)
    except Exception as exc:
        return f"网络检索失败：{exc}"
