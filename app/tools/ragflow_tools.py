"""RAGFlow knowledge-base tools with lazy client construction."""

from __future__ import annotations

import json
from functools import lru_cache

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from app.api.monitor import monitor
from app.core.settings import get_settings


@lru_cache(maxsize=1)
def _client() -> RAGFlow:
    settings = get_settings()
    if not settings.ragflow_api_url or not settings.ragflow_api_key:
        raise RuntimeError("未配置 RAGFLOW_API_URL 或 RAGFLOW_API_KEY。")
    return RAGFlow(api_key=settings.ragflow_api_key, base_url=settings.ragflow_api_url)


@tool
def get_assistant_list() -> str:
    """查询 RAGFlow 中可用的聊天助手及其关联知识库。"""
    monitor.report_tool("知识库助手发现：get_assistant_list", {})
    try:
        chats = _client().list_chats()
        if not chats:
            return "没有任何可用的 RAGFlow 助手。"
        lines = []
        for chat in chats:
            dataset_names = getattr(chat, "kb_names", []) or []
            lines.append(
                f"助手名称: {chat.name}; 功能介绍: {chat.description}; "
                f"关联知识库: {'、'.join(dataset_names) or '未标注'}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 RAGFlow 助手失败：{exc}"


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """向指定 RAGFlow 助手创建临时会话、提问并清理会话。"""
    monitor.report_tool(
        "知识库问答：create_ask_delete",
        {"chat_name": chat_name, "question": question},
    )
    session = None
    chat = None
    try:
        chats = _client().list_chats(name=chat_name)
        if not chats:
            return f"未找到名为 {chat_name} 的 RAGFlow 助手。"
        chat = chats[0]
        session = chat.create_session(name="nexus_ephemeral_session")
        response = _client().post(
            f"/chats/{chat.id}/completions",
            {
                "messages": [{"role": "user", "content": question}],
                "stream": True,
                "session_id": session.id,
            },
            stream=True,
        )
        result = ""
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            line = line.removeprefix("data:").strip()
            if line == "[DONE]":
                break
            data = json.loads(line)
            chunk_data = data.get("data")
            if not isinstance(chunk_data, dict):
                continue
            answer = chunk_data.get("answer")
            if answer:
                if answer.startswith(result):
                    result = answer
                elif not result.startswith(answer):
                    result += answer
        return result or "知识库未返回有效内容。"
    except Exception as exc:
        return f"知识库提问失败：{exc}"
    finally:
        if chat is not None and session is not None:
            try:
                chat.delete_sessions(ids=[session.id])
            except Exception:
                pass
