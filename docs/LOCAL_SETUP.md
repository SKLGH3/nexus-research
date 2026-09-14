# 本地部署与排障

## 环境要求

- Windows 10/11、macOS 或 Linux
- Python 3.12
- uv
- Node.js 20+
- pnpm 10+
- 默认 SQLite 模式不需要 Docker

## 后端启动

~~~powershell
Copy-Item .env.example .env
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv sync
uv run uvicorn app.api.server:app --host 127.0.0.1 --port 8010
~~~

检查以下地址：

- http://127.0.0.1:8010/api/health
- http://127.0.0.1:8010/api/config
- http://127.0.0.1:8010/docs

首次数据库访问会生成 app/data/nexus_demo.db。

## 前端启动

~~~powershell
Set-Location frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
~~~

访问 http://127.0.0.1:5173。

## 常见问题

### uv 缓存目录异常

Windows 上若全局缓存不可写或被异常文件占用，改用项目内缓存：

~~~powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv sync
~~~

### pnpm 提示 ignored builds / esbuild

~~~powershell
pnpm approve-builds
pnpm rebuild esbuild
pnpm build
~~~

只批准已核验的依赖安装脚本，不要批准未知包。

### 端口 8000 已被占用

先检查占用进程：

~~~powershell
netstat -ano | Select-String ':8000'
~~~

也可以改用其他端口，例如 8010：

~~~powershell
uv run uvicorn app.api.server:app --host 127.0.0.1 --port 8010
~~~

然后同步修改 frontend/.env 中的 VITE_API_BASE_URL 与 VITE_WS_BASE_URL，再重启前端。本次本地验证因 Docker Desktop 占用 8000，实际使用 8010。
### 后端能启动但任务返回 503

这是预期行为。填写 LLM_MODEL、LLM_API_KEY、LLM_BASE_URL 后重启后端。密钥不会通过 /api/config 返回前端。

### Tavily 或 RAGFlow 显示 SETUP

它们是可选能力。分别填写 TAVILY_API_KEY，或 RAGFLOW_API_URL 与 RAGFLOW_API_KEY 后重启。

### MySQL 连接失败

确认 DATABASE_DRIVER=mysql、端口、账号与数据库名，并给应用账号只读权限。示例端口 3307 不代表你的 MySQL 一定使用该端口。

### WebSocket 一直重连

确认后端已启动，VITE_WS_BASE_URL 与实际端口一致，CORS_ORIGINS 包含前端地址，并检查本机防火墙。

## 无模型密钥 smoke test

~~~powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run python -m compileall app
uv run python -c "from app.tools.db_tools import list_sql_tables; print(list_sql_tables.invoke({}))"
~~~

预期 Python 编译通过，SQLite 自动初始化，并返回 companies、market_signals、research_projects。




## v2.0 首次登录

后端第一次启动会创建 `app/data/nexus_app.db`，并根据 `.env` 的 `ADMIN_EMAIL`、`ADMIN_PASSWORD`、`ADMIN_NAME` 初始化管理员。默认本地邮箱为 `admin@nexus.local`；密码请直接查看并修改本地 `.env`，不要提交到版本库。

至少配置：

~~~env
APP_DATABASE_PATH=app/data/nexus_app.db
AUTH_SECRET=一段足够长的随机字符串
AUTH_TOKEN_HOURS=24
AUTH_ALLOW_REGISTRATION=true
ADMIN_EMAIL=admin@nexus.local
ADMIN_PASSWORD=替换为强密码
~~~

修改管理员密码后，如果管理员已创建，数据库中的密码不会自动覆盖；可删除仅用于本地开发的 `nexus_app.db` 后重启，或后续实现密码管理界面。删除数据库会同时清空用户与研究历史。
