"""FastAPI gateway for NEXUS Research."""

from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent.main_agent import run_deep_agent
from app.api.auth import admin_user, auth_response, authenticate, current_user, ensure_admin_user, register_user, websocket_user
from app.api.monitor import manager
from app.core.settings import get_settings
from app.data.store import (
    admin_stats, claim_session, create_or_restart_task, create_template, delete_task,
    delete_template, get_task, initialize_app_database, list_tasks, list_templates,
    list_users, public_user, user_owns_thread,
)
from app.tools.db_tools import database_status

APP_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = APP_ROOT / "output"
UPLOAD_ROOT = APP_ROOT / "updated"
OUTPUT_ROOT.mkdir(exist_ok=True)
UPLOAD_ROOT.mkdir(exist_ok=True)
THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".xlsx", ".xls", ".csv", ".tsv", ".md", ".txt", ".json"}
active_tasks: dict[str, asyncio.Task] = {}
settings = get_settings()
UserDep = Annotated[dict[str, Any], Depends(current_user)]
AdminDep = Annotated[dict[str, Any], Depends(admin_user)]


def _safe_thread_id(value: str | None) -> str:
    thread_id = value or str(uuid.uuid4())
    if not THREAD_ID_PATTERN.fullmatch(thread_id):
        raise HTTPException(status_code=422, detail="thread_id 格式不合法")
    return thread_id


def _session_dir(root: Path, thread_id: str) -> Path:
    safe_id = _safe_thread_id(thread_id)
    target = (root / f"session_{safe_id}").resolve()
    if target.parent != root.resolve():
        raise HTTPException(status_code=403, detail="非法会话路径")
    return target


def _session_file(thread_id: str, relative_path: str) -> Path:
    session_dir = _session_dir(OUTPUT_ROOT, thread_id)
    target = (session_dir / relative_path).resolve()
    if target != session_dir and session_dir not in target.parents:
        raise HTTPException(status_code=403, detail="非法文件路径")
    return target


def _require_owner(thread_id: str, user: dict[str, Any]) -> None:
    if user.get("role") != "admin" and not user_owns_thread(thread_id, user["id"]):
        raise HTTPException(status_code=404, detail="会话不存在")


def _files_for_thread(thread_id: str) -> list[dict[str, Any]]:
    session_dir = _session_dir(OUTPUT_ROOT, thread_id)
    if not session_dir.exists():
        return []
    files = []
    for file_path in session_dir.rglob("*"):
        if file_path.is_file():
            stat = file_path.stat()
            files.append({"name": file_path.name, "type": "file", "path": file_path.relative_to(session_dir).as_posix(), "size": stat.st_size, "mtime": stat.st_mtime})
    return sorted(files, key=lambda item: item["mtime"], reverse=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    manager.set_loop(asyncio.get_running_loop())
    database_status()
    initialize_app_database()
    ensure_admin_user()
    yield
    pending = [task for task in active_tasks.values() if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


app = FastAPI(title=f"{settings.app_name} API", version=settings.app_version, description="Multi-agent research orchestration, retrieval and artifact delivery API.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class TaskRequest(BaseModel):
    query: str = Field(min_length=2, max_length=12000)
    thread_id: str | None = None


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class TemplateCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    prompt: str = Field(min_length=5, max_length=12000)
    category: str = Field(default="自定义", min_length=1, max_length=60)
    is_public: bool = False


def _forget_task(thread_id: str, task: asyncio.Task) -> None:
    if active_tasks.get(thread_id) is task:
        active_tasks.pop(thread_id, None)


@app.get("/")
async def root():
    return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs"}


@app.get("/api/health")
async def health():
    summary = settings.public_summary()
    return {"status": "ok", "ready_for_tasks": settings.llm_ready, "database": database_status(), "integrations": summary["integrations"]}


@app.get("/api/config")
async def public_config():
    summary = settings.public_summary()
    summary["integrations"]["database"] = database_status()
    summary["allow_registration"] = settings.allow_registration
    return summary


@app.post("/api/auth/register")
async def auth_register(request: RegisterRequest):
    if not EMAIL_PATTERN.fullmatch(request.email.strip()):
        raise HTTPException(status_code=422, detail="邮箱格式不正确")
    try:
        user = register_user(request.email, request.display_name, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return auth_response(user)


@app.post("/api/auth/login")
async def auth_login(request: LoginRequest):
    user = authenticate(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return auth_response(user)


@app.get("/api/auth/me")
async def auth_me(user: UserDep):
    return public_user(user)


@app.get("/api/history")
async def history(user: UserDep, limit: int = 50):
    return {"items": list_tasks(user["id"], limit)}


@app.get("/api/history/{thread_id}")
async def history_detail(thread_id: str, user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    task = get_task(thread_id, user["id"], admin=user.get("role") == "admin")
    if not task:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    task["files"] = _files_for_thread(thread_id)
    return task


@app.delete("/api/history/{thread_id}")
async def history_delete(thread_id: str, user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    if not delete_task(thread_id, user["id"], admin=user.get("role") == "admin"):
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return {"status": "deleted", "thread_id": thread_id}


@app.get("/api/templates")
async def templates(user: UserDep):
    return {"items": list_templates(user["id"])}


@app.post("/api/templates")
async def template_create(request: TemplateCreateRequest, user: UserDep):
    return create_template(user["id"], request.model_dump(), is_admin=user.get("role") == "admin")


@app.delete("/api/templates/{template_id}")
async def template_delete(template_id: str, user: UserDep):
    if not delete_template(template_id, user["id"], is_admin=user.get("role") == "admin"):
        raise HTTPException(status_code=404, detail="模板不存在或不可删除")
    return {"status": "deleted", "template_id": template_id}


@app.get("/api/admin/overview")
async def admin_overview(_user: AdminDep):
    return admin_stats()


@app.get("/api/admin/users")
async def admin_users(_user: AdminDep):
    return {"items": list_users()}


@app.post("/api/task")
async def run_task(request: TaskRequest, user: UserDep):
    thread_id = _safe_thread_id(request.thread_id)
    if not settings.llm_ready:
        raise HTTPException(status_code=503, detail="模型尚未配置。请在 .env 中设置 LLM_MODEL 与 LLM_API_KEY。")
    try:
        create_or_restart_task(thread_id, user["id"], request.query.strip())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    old_task = active_tasks.get(thread_id)
    if old_task and not old_task.done():
        old_task.cancel()
    task = asyncio.create_task(run_deep_agent(request.query.strip(), thread_id))
    active_tasks[thread_id] = task
    task.add_done_callback(lambda finished: _forget_task(thread_id, finished))
    return {"status": "started", "thread_id": thread_id}


@app.post("/api/task/{thread_id}/cancel")
async def cancel_task(thread_id: str, user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    _require_owner(thread_id, user)
    task = active_tasks.get(thread_id)
    if not task or task.done():
        active_tasks.pop(thread_id, None)
        raise HTTPException(status_code=404, detail="任务不存在或已结束")
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
    except asyncio.CancelledError:
        _forget_task(thread_id, task)
    except asyncio.TimeoutError:
        return {"status": "cancelling", "thread_id": thread_id}
    except Exception:
        _forget_task(thread_id, task)
    return {"status": "cancelled", "thread_id": thread_id}


@app.post("/api/upload")
async def upload_files(files: Annotated[list[UploadFile], File()], thread_id: Annotated[str, Form()], user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    try:
        claim_session(thread_id, user["id"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    target_dir = _session_dir(UPLOAD_ROOT, thread_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    saved_files: list[str] = []
    for upload in files:
        safe_name = Path(upload.filename or "").name
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(status_code=415, detail=f"不支持的文件类型：{safe_name or '未命名文件'}")
        destination = target_dir / safe_name
        size = 0
        try:
            with destination.open("wb") as buffer:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(status_code=413, detail=f"文件 {safe_name} 超过 {settings.max_upload_mb}MB 限制")
                    buffer.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        saved_files.append(safe_name)
    return {"status": "uploaded", "files": saved_files}


@app.get("/api/sessions/{thread_id}/files")
async def list_session_files(thread_id: str, user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    _require_owner(thread_id, user)
    return {"files": _files_for_thread(thread_id)}


@app.get("/api/sessions/{thread_id}/files/{relative_path:path}")
async def download_session_file(thread_id: str, relative_path: str, user: UserDep):
    thread_id = _safe_thread_id(thread_id)
    _require_owner(thread_id, user)
    target = _session_file(thread_id, relative_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=target.name)


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    if not THREAD_ID_PATTERN.fullmatch(thread_id):
        await websocket.close(code=1008, reason="invalid thread id")
        return
    try:
        user = websocket_user(websocket)
        if get_task(thread_id) and user.get("role") != "admin" and not user_owns_thread(thread_id, user["id"]):
            await websocket.close(code=1008, reason="forbidden")
            return
    except HTTPException:
        await websocket.close(code=1008, reason="unauthorized")
        return
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "message": f"received: {data}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception:
        manager.disconnect(websocket, thread_id)


if __name__ == "__main__":
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=8010, reload=True)
