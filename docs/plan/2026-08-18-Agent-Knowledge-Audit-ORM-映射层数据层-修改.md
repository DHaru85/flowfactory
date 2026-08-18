# 2026-08-18 Agent/Knowledge/Audit ORM 扩展 - 映射层/数据层 - 修改

## 用户需求理解

扩展 Agent Configuration、Knowledge/Files/Retrieval、Audit and Usage 三域 ORM 与持久化仓储，并生成 Alembic 迁移应用到 flowfactory 库。

## 待澄清事项

无待澄清事项。

## 施工方案

1. 新增 `data_schema/agent`、`knowledge`、`audit` 模型，对齐 `data_schema_server.md`。
2. `kb_chunk` 启用 pgvector（1536 维可空）；`content_tsv` 列由应用层写入（zhparser 后续迁移补触发器）。
3. 新增 `service/persistence` 仓储：按域提供 create/get/list 基础操作。
4. Alembic autogenerate + upgrade；更新集成测试表清单。

## 方案待澄清事项

无待澄清事项（方案锁定）。

## 验收标准

1. ruff 检查通过（源码目录）。
2. 集成测试通过，新表均存在。
