# 模块施工状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 映射层 / data_schema（Permission） | 空闲 | ORM + 仓储已落地；User.roles 补 foreign_keys |
| 映射层 / data_schema（Conversation） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Workflow） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Agent） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Knowledge） | 空闲 | embedding 列 1024 维（bge-m3）；Alembic c4a91f2e7b10 |
| 映射层 / data_schema（Audit） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Graph） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Security） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Observability） | 空闲 | ORM + Collector flush 仓储查询 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | 异步引擎改为线程局部，适配 Celery prefork/eager |
| 数据层 / service/persistence | 空闲 | Observability 含 span_id 幂等查询 |
| 数据层 / service/cache | 空闲 | JwtCacheStore + GrantCacheStore |
| 数据层 / settings | 空闲 | JWT / LDAP / MinIO / embedding / OTel / LangFuse |
| 服务层 / service/runtime | 空闲 | LLM usage + 编译期节点包装 + envelope flush |
| 服务层 / service/celery_app | 空闲 | prefork 后重置观测 ContextVar |
| 服务层 / service/observability | 空闲 | TraceCollector / LangFuse 预留 / 脱敏 |
| 服务层 / service/orchestration | 空闲 | Passthrough + Temporal 骨架 |
| 服务层 / service/knowledge | 空闲 | 切片 / 向量化 / 检索 / 入库流水线 |
| 服务层 / service/storage | 空闲 | ObjectStore + MinIO public GET |
| 服务层 / service/auth | 空闲 | AuthService / PermissionService / LDAP 预留 |

未列出的模块视为 **空闲**。

## 施工简报

- 2026-08-19 知识检索：文本/MD/PDF 入库、可配置切片、bge-m3、RRF；pytest 已通过。
- 2026-08-19 用户鉴权：本地 Argon2 + JWT/refresh；RBAC；LDAP 协议/`Ldap3Adapter`/登录 bind 回退/JIT 映射/同步任务已预留。ruff 通过，pytest 48 passed。
- 2026-08-19 全链路可观测：TraceCollector flush `obs_*`；LangFuse 协议/Fake/SDK 预留；LLM usage；编译期节点包装。ruff 通过，pytest 57 passed。
