# 模块施工状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 映射层 / data_schema（Permission） | 空闲 | ORM + 仓储已落地；User.roles 补 foreign_keys |
| 映射层 / data_schema（Conversation） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Workflow） | 空闲 | `wf_child_run_pending` ORM + Alembic b7e2c91a4d03 |
| 映射层 / data_schema（Agent） | 空闲 | binding 含 application；主体索引 b1d8f4a06c31 |
| 映射层 / data_schema（Knowledge） | 空闲 | embedding 列 1024 维（bge-m3）；Alembic c4a91f2e7b10 |
| 映射层 / data_schema（Audit） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Graph） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Security） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Observability） | 空闲 | ORM + Collector flush 仓储查询 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | 异步引擎改为线程局部，适配 Celery prefork/eager |
| 数据层 / service/persistence | 空闲 | 按 binding 主体列出可见资源 id |
| 数据层 / service/cache | 空闲 | Redis 仅热状态；SSE 帧不走 Redis |
| 数据层 / settings | 空闲 | 默认 rabbitmq_url；stream 连接超时与投递超时分离 |
| 服务层 / service/runtime | 空闲 | compile 双读 v0/v1；HITL SSE `run_interrupted` |
| 服务层 / service/events | 空闲 | SSE 总线接现网 AMQP；connect 超时与 publish 超时分离 |
| 服务层 / service/celery_app | 空闲 | envelope `kind`；子图超时 tick |
| 服务层 / service/observability | 空闲 | TraceCollector / LangFuse 预留 / 脱敏 |
| 服务层 / service/orchestration | 空闲 | Passthrough + Temporal 骨架 |
| 服务层 / service/knowledge | 空闲 | 切片 / 向量化 / 检索 / 入库流水线 |
| 服务层 / service/storage | 空闲 | ObjectStore + MinIO public GET |
| 服务层 / service/auth | 空闲 | AccessControl；本地自助注册 |
| 服务层 / service/tools | 空闲 | ToolExecutor；SkillRuntime |
| docs/design（服务说明文档） | 空闲 | 流式总线默认接现网 RabbitMQ |
| 表示层 / frontend | 空闲 | Studio 下钻；HITL 待办与会话恢复 |
| 应用层 / api | 空闲 | HITL 待办列表与 resume |
| 服务层 / service/guardrail | 空闲 | GuardrailEvaluator / PolicyDetector 预留 |

未列出的模块视为 **空闲**。

## 施工简报

- 2026-08-20 SSE 总线：默认 `FLOWFACTORY_RABBITMQ_URL` 指向 `192.168.129.53:5672`；`AmqpStreamEventBus` 回环 speaking 成功；`ff.stream` 已 declare。连接超时与投递超时分离。ruff 通过；相关 pytest 7 passed。需重启 uvicorn 后现网 SSE 才走 AMQP。
- 2026-08-20 子图下钻与 HITL：Studio 面包屑只读下钻已发布子图；`GET/POST /conversations/workflow/hitl-pendings`；属主/超管；SSE `run_interrupted`。pytest `test_api_hitl` + SSE 机 9 passed；`npm run build` 通过。
- 2026-08-20 Studio 画布：`@xyflow/react`；`/studio` 列表与 `/studio/:flowId` 编辑器；坐标只写 `view`；拓扑走 nodes/edges/branches；`can_control` 才保存/发布/新草稿。`npm run build` 通过。
- 2026-08-20 登录跳转：`RequireAuth` / `GuestOnly` 在子组件渲染时判定会话，避免父级 `element` 冻住未登录状态。登录/注册成功进入 `AppShell`；已登录访问登录/注册页重定向 `/`。`npm run build` 通过。
- 2026-08-20 自助注册：`POST /api/v1/auth/register`；default 组织；首个未删除用户为超管；登录页「注册」入口。pytest `test_register_and_conflict` 通过；`npm run build` 通过。
- 2026-08-20 表示层首轮：`src/frontend` Vite + React + Antd / Ant Design X。登录 JWT、`/auth/apps` 菜单、models（密钥只写）、agent_config 与绑定、planner/workflow 会话与 fetch SSE。`npm run build` 通过。Studio 画布仍在 `docs/plan/unreached/`。
- 2026-08-20 表示层数据契约：新增 `docs/design/data_schema_client.md`（传输对象 / 可运行对象 / 视图模型）。已开放 HTTP 的 auth、会话 SSE、studio Flow v1、models、agent_config 与现网 JSON 对齐；知识库、图、护栏管理、审计、观测、通知、Run/HITL 管理等保留空章。不改 Python、不建 `src/frontend`。
- 2026-08-20 RBAC：双层绑定（应用 ∪ 配置资源）。平台管理员 ≡ `is_superuser`，全应用/全资源查看修改删除。models/studio/agent_config（含 Beat）两档：可见可用 vs 完全控制。普通人未绑定资源 404。Alembic b1d8f4a06c31。ruff 通过；相关 pytest 26 passed。前端仍在 `docs/plan/unreached/`。

- 2026-08-20 规划 Beat：`agent_beat_task.flow_id` 可空，`profile_id` FK 恰一（Alembic a9c3e1d04b72）。到期 `profile_id` 入队 `kind=planner`，不 compile Flow。HTTP `/beat-tasks` 互斥字段；仅 `flow_id` 仍可用。ruff 通过；相关 pytest 14 passed。RBAC 审核 / 前端仍在 `docs/plan/unreached/`。
- 2026-08-20 第 3 轮自研规划循环：`SkillRuntime` + `PlannerRuntime`（planner⇄tools，`planner_max_steps`）；Celery 仍 `run_langgraph_flow`，envelope `kind=planner`。`POST /conversations/planner/messages` 返回 `run_id`。完成回写 assistant 消息。不引入 deepagents。ruff 通过；相关 pytest 6 passed（含集成写库）。规划 Beat / RBAC 审核 / 前端仍在 `docs/plan/unreached/`。
- 2026-08-20 第 2 轮会话路径：`/api/v1/conversations/planner*` 与 `/workflow*` 分场景；旧 `/conversations*` 为 workflow 别名。`profile_id` 仅详情 `metadata`；列表不含。planner 发消息 `501 planner_runtime_not_ready`。不调用 `PermissionService`。ruff 通过；相关 pytest 6 passed（含集成）。规划循环见 `docs/plan/unreached/2026-08-20-自研自主规划循环-服务层应用层-修改.md`。
- 2026-08-20 第 1 轮配置与模型：应用 `models`（LLM CRUD、密钥打码、`resolve_llm_client`）与 `agent_config`（Profile/Skill/Tool/MCP、仅 Flow 的 Beat、bindings）。创建配置时登记 `sys_asset`。不调用 `PermissionService`。Alembic e4a1b8c27d90。规划循环/会话拆分/规划 Beat/RBAC 审核/前端方案在 `docs/plan/unreached/`。ruff 通过；相关 pytest 18 passed（含集成）。
- 2026-08-19 Runtime v1：`FlowRuntime.compile` 双读 v0/v1；按 NodeType 编译；`FlowBranch` 条件边；HITL 节点内 `interrupt()`；子图独立 Celery Run + `wf_child_run_pending` / `waiting_child`；超时/取消只取消子并 resume 父；取消父级联且不 resume。不调用 `PermissionService`。ruff 通过；相关 pytest 22 passed（单测）+ 集成 10 passed。
- 2026-08-19 Studio：应用 `studio` 提供 Flow v1 草稿/发布/新草稿与 Profile/LLM/Tool 只读目录。不改 `FlowRuntime.compile`（v1 尚不可执行）；不调用 `PermissionService`（仅 JWT）。ruff 通过；相关 pytest 12 passed。
- 2026-08-19 Flow 图定义：`agent_flow.definition` 规范为 schema_version=1（三槽 state、FlowNode discriminator、无条件边 + 条件分支、view 与逻辑分离）。子图为独立 Celery Run + `waiting_child`；子超时/取消只取消子并把 `SubgraphNodeResult` 还给父；取消父级联取消子。未改 Python / Alembic。
- 2026-08-19 流式总线：RabbitMQ `ff.stream` 与 Celery 任务队列隔离、独立连接、保守背压；LLM `stream` 打字机；护栏只作用于持久化 state。SSE 消费有界 `asyncio.Queue`。ruff 通过；相关 pytest 15 passed。
- 2026-08-19 服务说明：新增 `docs/design/service_layer.md`，覆盖支撑设施与业务服务的使用、原理、协作流程与扩展指南。
- 2026-08-19 知识检索：文本/MD/PDF 入库、可配置切片、bge-m3、RRF；pytest 已通过。
- 2026-08-19 用户鉴权：本地 Argon2 + JWT/refresh；RBAC；LDAP 协议/`Ldap3Adapter`/登录 bind 回退/JIT 映射/同步任务已预留。ruff 通过，pytest 48 passed。
- 2026-08-19 全链路可观测：TraceCollector flush `obs_*`；LangFuse 协议/Fake/SDK 预留；LLM usage；编译期节点包装。ruff 通过，pytest 57 passed。
- 2026-08-19 工具分发：ToolExecutor 按 kind 分发；`kb_retrieve`；HTTP URL 仅来自配置；MCP 协议/Fake/SDK 预留。ruff 通过，pytest 66 passed。
