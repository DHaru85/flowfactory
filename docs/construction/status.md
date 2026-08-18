# 模块施工状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 映射层 / data_schema（Permission） | 空闲 | ORM + 仓储已落地；User.roles 补 foreign_keys |
| 映射层 / data_schema（Conversation） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Workflow） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Agent） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Knowledge） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Audit） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Graph） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Security） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Observability） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | 异步引擎改为线程局部，适配 Celery prefork/eager |
| 数据层 / service/persistence | 空闲 | 全域仓储 async 适配 |
| 数据层 / service/cache | 空闲 | Redis 默认 192.168.129.53:6479 db=4；WorkflowCacheStore |
| 服务层 / service/runtime | 空闲 | LangGraph + vLLM + HITL + Beat |
| 服务层 / service/celery_app | 空闲 | Celery eager / prefork 调度 |
| 服务层 / service/orchestration | 空闲 | Passthrough + Temporal 骨架 |

未列出的模块视为 **空闲**。
