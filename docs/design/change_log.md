# 变更日志记录

| 时间 | 涉及模块 | 相关需求 | 变更说明 |
| --- | --- | --- | --- |
| 2026.08.18 14:06 | - | - | 添加项目整体架构选型和施工规范说明 |
| 2026.08.18 14:06 | docs/design | 添加设计文档 | 添加变更日志、数据结构设计说明文档 |
| 2026.08.18 15:04 | docs/design/data_schema.md | 补齐数据结构设计缺口 | 新增应用/服务注册、工作流运行与调度、对象存储、领域图、安全限流、可观测性、通知；身份同步与刷新令牌并入权限域；Checkpoint 拆成定义与实例 |
| 2026.08.18 15:18 | docs/design/data_schema.md | 澄清应用/服务与运行态形态 | Application/Service 改为纯 InMemoryEntity（代码引用，无字段关联）；去掉 Binding 表；Run/Thread 为调度单位且可持久化结果与 HITL/Beat 现场；Checkpoint Instance 为从 PG 读出的内存对象 |
| 2026.08.18 15:27 | docs/design/data_schema.md | 三类形态重组文档结构 | 各功能域下统一分为 数据 / 可运行对象 / 序列化对象；Run/Thread 快照等归入数据，运行时实例归入可运行对象 |
| 2026.08.18 15:39 | docs/design/data_schema_server.md | Permission 域五级展开 | User/Org/Dept/Role/Assets/Quota/RefreshToken/Ldap/Redis JWT 表与 key；LdapAdapter/AuthService/PermissionService 方法与 Pydantic Schema |
| 2026.08.18 15:40 | docs/design/data_schema_server.md | 四域五级展开 | Application/Service Registry、Conversation/SSE、Agent Configuration、Workflow Execution 表结构、Redis key、可运行对象方法与 Schema |
| 2026.08.18 15:41 | docs/design/data_schema_server.md | 剩余六域五级展开 | Knowledge/Graph/Security/Audit/Observability/Notification 全文档五级结构完成 |
| 2026.08.18 16:10 | src/backend | ORM 与 PG 数据层首版 | Permission/Conversation/Workflow 三域 ORM；service/database；Alembic 迁移；flowfactory 库已创建 |
| 2026.08.18 17:11 | src/backend | Agent/Knowledge/Audit ORM 扩展 | 三域 ORM + service/persistence 仓储；pgvector 扩展；Alembic d8fe5039a9d1 |
| 2026.08.18 17:20 | src/backend | 剩余映射层与数据层 | Graph/Security/Observability/Notification ORM；全域仓储与 factory；Redis cache；Alembic 00fe9d0489d1（共 49 表） |
| 2026.08.18 17:30 | src/backend | PG 异步连接池 | create_async_engine + AsyncSession；pool_size 默认 20；仓储 async 适配 |
| 2026.08.18 18:00 | src/backend | 工作流运行时环境 | Celery eager 调度；LangGraph + Postgres checkpointer；vLLM OpenAI 兼容 LLM；HITL/Beat；Temporal 骨架 |
