"""Main multi-agent orchestration and session execution."""

from __future__ import annotations

import asyncio
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.llm import get_model
from app.agent.prompts import main_agent_content
from app.agent.subagents.database_query_agent import database_query_agent
from app.agent.subagents.knowledge_base_agent import knowledge_base_agent
from app.agent.subagents.network_search_agent import network_search_agent
from app.api.context import reset_session_context, set_session_context, set_thread_context
from app.api.monitor import monitor
from app.tools.markdown_tools import generate_markdown
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content

APP_ROOT = Path(__file__).parents[1].resolve()


@lru_cache(maxsize=1)
def get_main_agent():
    """Construct the agent graph lazily so the API can boot before secrets exist."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=[generate_markdown, convert_md_to_pdf, read_file_content],
        checkpointer=InMemorySaver(),
        subagents=[database_query_agent, network_search_agent, knowledge_base_agent],
    )


def _message_text(content: Any) -> str:
    """Normalize LangChain text or multimodal content into display text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return str(content).strip() if content else ""


async def run_deep_agent(task_query: str, session_id: str) -> None:
    """Execute one research task and stream observability events to the UI."""
    session_dir = APP_ROOT / "output" / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir_str = session_dir.as_posix()
    relative_session_dir = session_dir.relative_to(APP_ROOT).as_posix()

    upload_dir = APP_ROOT / "updated" / f"session_{session_id}"
    upload_prompt = ""
    if upload_dir.exists():
        files = [item for item in upload_dir.iterdir() if item.is_file()]
        for source in files:
            shutil.copy2(source, session_dir / source.name)
        if files:
            upload_prompt = (
                "\n[已上传文件]\n"
                + "\n".join(f"- {item.name}" for item in files)
                + "\n请先调用 read_file_content 阅读与任务相关的附件。"
            )

    session_token = set_session_context(session_dir_str)
    thread_token = set_thread_context(session_id)
    monitor.report_session_dir(session_dir_str)

    config = {"configurable": {"thread_id": session_id}}
    instruction = f"""

【当前任务工作区】
- 工作目录：{relative_session_dir}
- 所有新文件必须写入这个目录
- 读取附件时只把文件名传给 read_file_content
- 使用相对路径，不得访问工作目录之外的位置
{upload_prompt}
"""

    final_content = ""
    try:
        agent = get_main_agent()
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": task_query + instruction}]},
            config=config,
        ):
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue
                messages = state["messages"]
                if not isinstance(messages, list) or not messages:
                    continue
                last_message = messages[-1]
                tool_calls = getattr(last_message, "tool_calls", None) or []
                if node_name == "model" and tool_calls:
                    for tool_call in tool_calls:
                        if tool_call.get("name") != "task":
                            continue
                        arguments = tool_call.get("args") or {}
                        monitor.report_assistant(
                            str(arguments.get("subagent_type", "专家助手")),
                            {"description": arguments.get("description", "")},
                        )
                elif node_name == "model":
                    text = _message_text(getattr(last_message, "content", ""))
                    if text:
                        final_content = text

        if not final_content:
            final_content = "任务已执行完成，但模型没有返回可展示的文本结果。"
        monitor.report_task_result(final_content)
    except asyncio.CancelledError:
        monitor.report_task_cancelled()
        raise
    except Exception as exc:
        monitor.report_error(f"任务执行失败：{exc}")
    finally:
        reset_session_context(session_token, thread_token)
