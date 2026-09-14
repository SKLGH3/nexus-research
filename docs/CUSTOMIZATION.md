# 定制指南

## 模型接口

系统使用 LangChain ChatOpenAI 兼容接口。在根目录 .env 配置 LLM_PROVIDER、LLM_MODEL、LLM_API_KEY 与 LLM_BASE_URL。若供应商不是 OpenAI-compatible，需要在 app/agent/llm.py 增加 provider 分支，并保持 get_model() 返回 LangChain chat model。

## 数据库

默认 SQLite 结构和种子数据位于 app/data/bootstrap.py。可替换种子数据，或将 DATABASE_DRIVER 改为 mysql。数据库专家会先发现表、再预览、再查询，不依赖固定业务表。

新增数据库类型时，在 app/tools/db_tools.py 扩展连接、表发现和标识符引用规则，同时保留只读限制与结果上限。

## Agent 与工具

- 修改主 Agent：app/prompt/prompts.yml 的 main_agent。
- 修改专家边界：同文件的 sub_agents。
- 新增工具：在 app/tools 下实现 LangChain tool，并注册到目标 Agent 的 tools 数组。
- 新增专家：创建 app/agent/subagents/<name>.py，并注册到 get_main_agent() 的 subagents 数组。
- 新增可观察事件：后端 monitor 与前端类型、Hook 要同步修改。

## 品牌与视觉

- 品牌名：VITE_APP_NAME
- 副标题：VITE_APP_TAGLINE
- 页面结构：frontend/src/App.tsx
- 全局视觉：frontend/src/styles.css
- Ant Design token：frontend/src/main.tsx
- 浏览器标题：frontend/index.html

当前设计为暖白纸张背景、深海军蓝命令侧栏、珊瑚色重点。继续换品牌时优先修改 CSS 变量与环境变量，不要在业务组件散落颜色。

## 新功能落点

- 引用管理：给 monitor 事件增加 sources，在前端增加可折叠来源面板。
- 研究模板：维护模板库，把结构化模板拼入任务输入。
- 任务历史：将 active_tasks 和结果持久化，新增历史 API。
- 多模型路由：在 get_model 或主 Agent 前增加模型选择策略。
- 权限：为 FastAPI 增加认证依赖，让 thread_id 绑定用户身份。
- 导出：新增 CSV/XLSX 工具并注册给主 Agent。

## 改造成独立项目的发布清单

1. 确认上游许可证和授权范围。
2. 替换品牌名、Logo、示例数据、文案和截图。
3. 删除未使用的旧组件与教学脚本。
4. 添加自己的 LICENSE、隐私说明与安全策略。
5. 使用密钥管理服务，不提交 .env。
6. 增加认证、审计、队列、对象存储和监控。
7. 建立单元测试、端到端测试、依赖升级与漏洞扫描。


## v2.0 产品化扩展点

- 品牌与文案：`frontend/src/lib/config.ts`、`frontend/src/App.tsx`、`frontend/src/styles.css`。
- 登录与权限：`app/api/auth.py`。生产环境可替换为企业 SSO/OIDC，并保持 `current_user` 依赖契约。
- 研究资产：`app/data/store.py`。如需 PostgreSQL，可按现有函数接口实现新的仓储层。
- 研究模板：内置模板在 `DEFAULT_TEMPLATES`，用户模板通过 `/api/templates` 管理。
- 证据系统：工具调用 `monitor.report_sources()` 即可让来源进入 WebSocket、数据库和前端引用面板。
- 管理中心：`/api/admin/overview` 和 `/api/admin/users` 只允许 `admin` 角色访问。
