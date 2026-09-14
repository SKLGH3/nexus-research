# NEXUS Research / 智研中枢

一个可本地运行、可替换模型供应商、支持多来源检索与文件交付的多智能体研究工作台。

本项目基于 didilili/deepsearch-agents 二次改造，增加统一配置、SQLite 零 Docker 演示库、外部服务延迟初始化、更安全的文件与数据库接口，并将界面改为暖白编辑部、深海军蓝侧栏和珊瑚色强调的 Research Command Center 风格。

> 上游来源与授权提醒见 NOTICE.md。公开发布或商用前，请确认上游许可证和授权范围。

## 核心能力

- 主智能体规划并路由网络研究、数据库分析、RAGFlow 知识库专家。
- 使用 OpenAI-compatible 模型接口，可通过环境变量切换模型和 Base URL。
- 默认自动初始化 SQLite 示例库，无需 Docker；也可切换 MySQL。
- 支持上传 PDF、Word、Excel、Markdown 和文本附件。
- WebSocket 实时展示工具调用、专家调度、结果、取消和异常。
- 支持生成 Markdown 与 PDF，并按会话安全浏览和下载。
- v2.0 增加注册登录、用户/管理员权限、研究历史持久化、证据来源、研究模板和管理中心。

## 快速启动

### 后端

要求 Python 3.12 与 uv。

~~~powershell
Copy-Item .env.example .env
# 编辑 .env；只有执行研究任务时才必须填写 LLM_MODEL 和 LLM_API_KEY
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv sync
uv run uvicorn app.api.server:app --host 127.0.0.1 --port 8010
~~~

未配置模型密钥时，API、健康检查与 SQLite 仍可启动；提交研究任务会返回明确的 503 配置提示。

### 前端

~~~powershell
Set-Location frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
~~~

访问 http://127.0.0.1:5173，后端接口文档位于 http://127.0.0.1:8010/docs。

## 常用配置

~~~env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5-mini
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
DATABASE_DRIVER=sqlite
SQLITE_PATH=app/data/nexus_demo.db
APP_DATABASE_PATH=app/data/nexus_app.db
AUTH_SECRET=请替换为长随机字符串
ADMIN_EMAIL=admin@nexus.local
ADMIN_PASSWORD=请设置强密码
~~~

切换 MySQL 时将 DATABASE_DRIVER 改为 mysql，并配置 MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD 与 MYSQL_DATABASE。新配置兼容旧变量 LLM_QWEN_MAX、OPENAI_API_KEY 和 OPENAI_BASE_URL。

## 项目结构

~~~text
app/
  agent/        模型工厂、主 Agent 和专家子 Agent
  api/          FastAPI、WebSocket、任务监控、请求上下文
  core/         统一配置
  data/         业务演示库初始化 + 用户/任务/模板/引用持久化
  prompt/       主/子 Agent 提示词
  tools/        网络、数据库、知识库、附件与文档工具
frontend/src/
  components/   对话、执行轨迹、附件与产物组件
  hooks/        会话状态、WebSocket 与轮询
  lib/          HTTP/WS 配置、API 客户端、thread_id
  App.tsx       Research Command Center 主界面
  styles.css    新品牌视觉系统
~~~

## 深入文档

- docs/ARCHITECTURE.md：完整架构与调用链
- docs/LOCAL_SETUP.md：本地部署、验证与排障
- docs/CUSTOMIZATION.md：模型、数据库、Agent、工具与品牌定制
- NOTICE.md：上游来源和授权提醒

## 验证

~~~powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run python -m compileall app
uv run python -m unittest discover -s tests -v
Set-Location frontend
pnpm build
~~~

当前 v2.0 已具备本地身份认证和持久化研究资产，适合本地开发与内部部署。生产环境仍建议接入成熟 IdP、Redis/持久化任务队列、对象存储、审计、限流、密钥托管和更严格的多租户隔离。
