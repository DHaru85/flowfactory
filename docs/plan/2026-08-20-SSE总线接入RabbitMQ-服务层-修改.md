# 2026-08-20 SSE 总线接入现网 RabbitMQ - 服务层 - 修改

## 用户需求理解

检查当前 SSE 流式总线是否已正确接入 RabbitMQ。若尚未接入，使用现网实例：

- host `192.168.129.53`
- AMQP `5672` / 管理口 `15672`
- 账号 `admin` / `Hisign123`

检查结论（施工前）：

1. **协议与代码已落地**：`api/sse/bus.py` 走 `get_stream_bus()`；`AmqpStreamEventBus`（aio-pika）按 `ff.stream` topic、`conv.{id}` routing key 实现；Redis 只做在场登记。
2. **运行时未接入**：`FLOWFACTORY_RABBITMQ_URL` 默认空字符串，工厂返回 `FakeStreamEventBus`（进程内 Queue）。当前 uvicorn **没有**连上 RabbitMQ。
3. **现网探测**：`192.168.129.53:5672` / `15672` 可达，管理 API 认证成功（RabbitMQ 3.13.7）；exchange `ff.stream` **不存在**（从未有进程成功 declare）。
4. **即便填上 URL，现有超时也会连不上**：`stream_publish_timeout_seconds` 默认 `0.2`，且包住 `_ensure()` 与 `connect_robust`。握手常超过 200ms，失败后只打日志、丢帧，表现为「接了但没事件」。

本期只把 **SSE 流式总线**接到该 RabbitMQ。**不**把 `celery_eager` 改为 false（任务仍可在 API 进程 eager 执行；跨进程任务投递是另一事项）。

## 需求中的待澄清事项

无待澄清事项

## 施工方案

### 1. 默认 broker URL

`Settings.rabbitmq_url` 默认改为：

`amqp://admin:Hisign123@192.168.129.53:5672/`

仍可用环境变量 `FLOWFACTORY_RABBITMQ_URL` 覆盖。工厂逻辑不变：非空 URL → `AmqpStreamEventBus`。

`celery_eager` 保持 `true`：Celery 任务不强制走队列；流式帧走独立 AMQP 连接。

### 2. 连接超时与投递超时分离

新增 `stream_connect_timeout_seconds`（默认 8 秒），仅用于 `connect_robust` / 首次 `_ensure`。

`stream_publish_timeout_seconds`（0.2）只约束 **已建立连接后的 publish**，符合「流式可丢帧、不堵任务通道」。

### 3. 文档

`docs/design/service_layer.md`：默认已填现网 AMQP URL；无 URL 时仍 Fake。`celery_eager` 与 broker 解耦说明一句。

### 4. 验收

- 对现网 RabbitMQ 做一次 subscribe → publish → consume 回环；管理口可见 `ff.stream`。
- Fake 单测仍通过；不把真实 MQ 作为 pytest 必选。
- ruff 无 error。

## 方案待澄清事项

无待澄清事项
