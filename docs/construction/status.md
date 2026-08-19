# 模块施工状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 映射层 / data_schema（Permission） | 空闲 | ORM + 仓储已落地；User.roles 补 foreign_keys |
| 映射层 / data_schema（Conversation） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Workflow） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Agent） | 空闲 | ORM + get_tool_by_code / get_mcp_server |
| 映射层 / data_schema（Knowledge） | 空闲 | embedding 列 1024 维（bge-m3）；Alembic c4a91f2e7b10 |
| 映射层 / data_schema（Audit） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Graph） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Security） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Observability） | 空闲 | ORM + Collector flush 仓储查询 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | 异步引擎改为线程局部，适配 Celery prefork/eager |
| 数据层 / service/persistence | 空闲 | Agent 工具按 code 查询 |
| 数据层 / service/cache | 空闲 | Redis 仅热状态；SSE 帧不走 Redis |
| 数据层 / settings | 空闲 | 含 stream_exchange / prefetch |
| 服务层 / service/runtime | 空闲 | LLM stream；speaking 不经护栏 |
| 服务层 / service/events | 空闲 | StreamEventBus Fake / AMQP ff.stream |
| 服务层 / service/celery_app | 空闲 | fork 后 reset stream bus |
| 服务层 / service/observability | 空闲 | TraceCollector / LangFuse 预留 / 脱敏 |
| 服务层 / service/orchestration | 空闲 | Passthrough + Temporal 骨架 |
| 服务层 / service/knowledge | 空闲 | 切片 / 向量化 / 检索 / 入库流水线 |
| 服务层 / service/storage | 空闲 | ObjectStore + MinIO public GET |
| 服务层 / service/auth | 空闲 | AuthService / PermissionService / LDAP 预留 |
| 服务层 / service/tools | 空闲 | ToolExecutor 分发 builtin/http/mcp |
| docs/design（服务说明文档） | 空闲 | 含 events 总线章 |
| 应用层 / api | 空闲 | SSE：MQ sub → asyncio.Queue |
| 服务层 / service/guardrail | 空闲 | GuardrailEvaluator / PolicyDetector 预留 |

未列出的模块视为 **空闲**。

## 施工简报

- 2026-08-19 流式总线：RabbitMQ `ff.stream` 与 Celery 任务队列隔离、独立连接、保守背压；LLM `stream` 打字机；护栏只作用于持久化 state。SSE 消费有界 `asyncio.Queue`。ruff 通过；相关 pytest 15 passed。
- 2026-08-19 服务说明：新增 `docs/design/service_layer.md`，覆盖支撑设施与业务服务的使用、原理、协作流程与扩展指南。
- 2026-08-19 知识检索：文本/MD/PDF 入库、可配置切片、bge-m3、RRF；pytest 已通过。
- 2026-08-19 用户鉴权：本地 Argon2 + JWT/refresh；RBAC；LDAP 协议/`Ldap3Adapter`/登录 bind 回退/JIT 映射/同步任务已预留。ruff 通过，pytest 48 passed。
- 2026-08-19 全链路可观测：TraceCollector flush `obs_*`；LangFuse 协议/Fake/SDK 预留；LLM usage；编译期节点包装。ruff 通过，pytest 57 passed。
- 2026-08-19 工具分发：ToolExecutor 按 kind 分发；`kb_retrieve`；HTTP URL 仅来自配置；MCP 协议/Fake/SDK 预留。ruff 通过，pytest 66 passed。
