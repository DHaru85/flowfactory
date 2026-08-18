# 模块施工状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 映射层 / data_schema（Permission） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Conversation） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Workflow） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Agent） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Knowledge） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Audit） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Graph） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Security） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Observability） | 空闲 | ORM + 仓储已落地 |
| 映射层 / data_schema（Notification） | 空闲 | ORM + 仓储已落地 |
| 数据层 / service/database | 空闲 | PG 异步连接池（pool_size=20） |
| 数据层 / service/persistence | 空闲 | 全域仓储 async 适配 |
| 数据层 / service/cache | 空闲 | Redis 客户端与 key/stores 封装 |

未列出的模块视为 **空闲**。
