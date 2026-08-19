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
| 映射层 / data_schema（Observability） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | 异步引擎改为线程局部，适配 Celery prefork/eager |
| 数据层 / service/persistence | 空闲 | Knowledge 仓储含向量/全文检索与替换切片 |
| 数据层 / service/cache | 空闲 | Redis 默认 192.168.129.53:6479 db=4；WorkflowCacheStore |
| 数据层 / settings | 空闲 | MinIO / bge-m3 / 切片策略 / ONNX 路径 |
| 服务层 / service/runtime | 空闲 | LangGraph + vLLM + HITL + Beat |
| 服务层 / service/celery_app | 空闲 | 含 ingest 任务与 kb.ingest 队列 |
| 服务层 / service/orchestration | 空闲 | Passthrough + Temporal 骨架 |
| 服务层 / service/knowledge | 空闲 | 切片 / 向量化 / 检索 / 入库流水线 |
| 服务层 / service/storage | 空闲 | ObjectStore + MinIO public GET |

未列出的模块视为 **空闲**。

## 2026-08-19 施工简报

知识检索服务层已落地：UTF-8 / Markdown / PDF 入库；切片策略 `recursive` / `markdown` / `fixed` / `page` 可配；embedding 默认 bge-m3（1024 维）；检索为 pgvector + tsvector + RRF；重排 ONNX 路径可配，未配置时 Identity。ruff 通过，pytest 36 passed。
