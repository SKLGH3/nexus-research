# NEXUS Research 项目架构与调用链

## 1. 系统定位

NEXUS Research 是前后端分离的多智能体研究工作台。React 负责输入、执行轨迹和产物展示；FastAPI 负责会话、异步任务、上传下载和 WebSocket；DeepAgents 负责规划、专家路由和工具调用；SQLite/MySQL、Tavily、RAGFlow 与本地文件工具提供真实数据能力。

## 2. 模块逐层说明

### 前端

- frontend/src/App.tsx：工作台骨架，组合品牌侧栏、能力矩阵、指标、消息流和输入器。
- frontend/src/hooks/useDeepAgentSession.ts：管理 thread_id、HTTP、WebSocket 重连、事件、文件轮询、取消和上传。
- frontend/src/components/ConversationThread.tsx：显示用户任务、执行轨迹、最终回答和产物下载。
- frontend/src/components/ChatComposer.tsx：任务输入、附件上传、新会话和取消。
- frontend/src/lib/api.ts：封装后端契约，文件下载只传 thread_id 与相对路径。
- frontend/src/lib/config.ts：统一 API、WebSocket 和品牌环境变量。

### API 与运行时

- app/api/server.py：FastAPI 入口、CORS、生命周期、任务表、上传下载、WebSocket。
- app/api/context.py：用 ContextVar 隔离 session_dir 与 thread_id，避免并发串台。
- app/api/monitor.py：将工具、专家、结果、取消和异常封装为 WebSocket 事件。
- app/core/settings.py：集中读取应用、模型、数据库与集成配置。

### Agent

- app/agent/llm.py：根据 LLM_* 配置构建 OpenAI-compatible ChatOpenAI，采用延迟创建。
- app/agent/main_agent.py：延迟构建 DeepAgent 图，创建会话目录，复制附件，注入工作区约束并消费流事件。
- app/agent/subagents：网络研究、数据分析、知识库专家的路由描述和工具集合。
- app/prompt/prompts.yml：主 Agent 与子 Agent 的行为策略。

### 工具与数据

- app/tools/tavily_tool.py：按需初始化 Tavily，负责公开网络检索。
- app/tools/db_tools.py：SQLite/MySQL 适配、表发现、样例预览、只读 SQL 与 200 行上限。
- app/data/bootstrap.py：首次访问时创建 SQLite 演示库并写入企业、市场信号和研究项目数据。
- app/tools/ragflow_tools.py：按需初始化 RAGFlow，发现助手、创建临时会话、提问并清理。
- app/tools/upload_file_read_tool.py：读取当前会话内附件。
- app/tools/markdown_tools.py 与 app/tools/pdf_tools.py：生成交付物。

## 3. 主请求调用链

~~~text
React App
  → useDeepAgentSession.submitTask(query)
  → POST /api/task { query, thread_id }
  → FastAPI 校验 thread_id、查询长度、LLM readiness
  → active_tasks[thread_id] = asyncio.create_task(...)
  → run_deep_agent(query, thread_id)
  → 创建 app/output/session_<thread_id>
  → 复制 app/updated/session_<thread_id> 中的附件
  → 写入 ContextVar(session_dir, thread_id)
  → get_main_agent() 延迟构建 DeepAgents 图
  → 主 Agent 规划并调用专家或本地工具
  → 主 Agent 汇总最终文本
  → monitor.report_task_result(...)
  → WebSocket /ws/{thread_id}
  → useDeepAgentSession 更新 events/result/files
  → ConversationThread / ArtifactShelf 渲染
~~~

## 4. Agent 调度链

~~~text
主 Agent
  ├─ task(network_search_agent)
  │    └─ internet_search → Tavily API
  ├─ task(database_query_agent)
  │    └─ list_sql_tables
  │         → get_table_data
  │         → execute_sql_query
  │              → SQLite 或 MySQL
  ├─ task(knowledge_base_agent)
  │    └─ get_assistant_list
  │         → create_ask_delete → RAGFlow
  ├─ read_file_content → 当前会话附件
  └─ generate_markdown → convert_md_to_pdf
~~~

路由原则是先发现真实能力和数据，再检索与交叉核验，最后汇总或生成文件。模型没有密钥时 Agent 图不会在 API 启动阶段创建，因此健康检查仍可用。

## 5. WebSocket 事件链

1. 浏览器以当前 thread_id 连接 /ws/{thread_id}。
2. ConnectionManager 保存 thread_id 到 WebSocket 的映射。
3. 工具通过 monitor.report_tool 报告 tool_start。
4. 主 Agent 检测到 task 工具调用时报告 assistant_call。
5. 会话目录、最终结果、取消和异常分别产生 session_created、task_result、task_cancelled、error。
6. Hook 最多保留 120 条事件，结束时刷新文件列表。
7. 断线两秒后重连，定时 ping 保持连接。

## 6. 上传与产物链

~~~text
ChatComposer 选择文件
  → POST /api/upload multipart/form-data
  → 校验 thread_id、扩展名、单文件大小
  → 分块写入 app/updated/session_<thread_id>
  → 任务启动时复制到 app/output/session_<thread_id>
  → read_file_content 仅在当前会话目录读取
  → 生成 Markdown/PDF 到同一输出目录
  → GET /api/sessions/{thread_id}/files
  → GET /api/sessions/{thread_id}/files/{relative_path}
~~~

路径安全由 thread_id 校验、文件名 basename、路径解析后确认仍位于会话目录内共同保证。前端不再传服务器绝对路径。

## 7. 数据库链与安全边界

- DATABASE_DRIVER=sqlite 时，首次连接自动执行 ensure_demo_database。
- DATABASE_DRIVER=mysql 时，从统一 Settings 创建连接。
- 表名只允许字母、数字、下划线且不能以数字开头。
- SQL 只允许 SELECT、WITH、SHOW、DESCRIBE、DESC 或 EXPLAIN 开头。
- 拒绝多语句和写入/DDL 关键词，结果最多返回 200 行。
- CSV writer 负责处理逗号、引号和换行。
- 生产环境仍应使用数据库只读账号，因为应用校验不能替代数据库权限。

## 8. 配置加载链

~~~text
进程环境 / 根目录 .env
  → dotenv.load_dotenv
  → get_settings() 单例缓存
  → FastAPI / 模型工厂 / 工具读取同一配置
  → GET /api/config 只返回非敏感 readiness
  → 前端能力矩阵显示 READY / SETUP
~~~

修改 .env 后需重启后端。测试动态修改环境变量时应调用 get_settings.cache_clear()。

## 9. 错误与取消链

- 配置缺失：提交任务前返回 HTTP 503，不影响服务启动。
- 工具异常：工具返回可读错误或 monitor 推送 error。
- 用户取消：取消 active_tasks 中对应 asyncio.Task，Agent 捕获 CancelledError 并推送 task_cancelled。
- 同会话新任务：已有未完成任务时先取消旧任务。
- 应用关闭：lifespan 取消并等待后台任务。
- WebSocket 断开：移除映射；浏览器自动重连，后台任务仍可继续。

## 10. 当前局限与生产化路线

- InMemorySaver 和 active_tasks 都是单进程内存状态，重启即失效。
- WebSocket 映射只存在于单进程；多实例需要 Redis Pub/Sub 或消息总线。
- 本地文件目录需要升级为对象存储、病毒扫描、配额和租户隔离。
- 当前没有登录、RBAC、审计和速率限制。
- SQL 防护应叠加只读用户、查询超时和资源配额。
- 长任务建议迁移到 Celery、RQ、Dramatiq 或云任务队列。
- 检索结果可增加结构化引用、去重、质量评分和缓存。
- Agent 流事件与 deepagents 0.5.7 耦合，升级前需要回归测试。


## 8. v2.0 身份与研究资产层

- `app/api/auth.py`：PBKDF2-SHA256 密码哈希、HMAC 签名访问令牌、HTTP/WebSocket 鉴权与管理员引导。
- `app/data/store.py`：独立 `nexus_app.db`，持久化用户、会话、任务、事件、引用和模板。业务演示数据继续保存在 `nexus_demo.db`，两者职责分离。
- `AuthGate.tsx`：登录/注册入口。
- `WorkspaceDrawer.tsx`：历史任务、研究模板和管理员统计。
- `ConversationThread.tsx`：在最终结论下展示结构化证据来源，并通过鉴权 fetch 下载产物。

### 鉴权调用链

~~~text
登录/注册 → /api/auth/* → 校验密码或创建用户 → 签发 HMAC token
后续 HTTP → Authorization: Bearer <token> → current_user → 资源所有权校验
WebSocket → /ws/{thread_id}?token=... → websocket_user → 会话所有权校验
~~~

### 持久化与引用调用链

~~~text
POST /api/task → claim_session → create_or_restart_task(status=running)
Agent/Tool → monitor._emit → task_events
Tavily → monitor.report_sources → citations 去重持久化
任务完成/失败/取消 → research_tasks 状态与结果更新
GET /api/history/{thread_id} → 任务 + 事件 + 引用 + 输出文件
~~~

### 数据表

`users` → `research_sessions` → `research_tasks` / `task_events` / `citations`；`research_templates` 支持内置公开模板和用户私人模板。所有外键启用，SQLite 使用 WAL。
