# FLowFactory 后端服务API说明文档

本文描述 **2026-08-19 应用层首批接口**（FastAPI）。服务层能力见 [service_layer.md](./service_layer.md)；表结构见 [data_schema_server.md](./data_schema_server.md)。

- 基址前缀：`/api/v1`（健康检查除外）。
- 鉴权：除登录、刷新、`GET /health` 外，请求头 `Authorization: Bearer <access_token>`。
- 错误体：`{"code": string, "message": string}`。
- 本轮无限流 HTTP。SSE 中继为 RabbitMQ topic `ff.stream`（与 Celery 任务队列隔离）；Redis 只做断线缓冲与在场登记。
- 流式 `speaking` **不经内容护栏**；护栏作用于节点完成后的持久化 state。

## 1. 健康检查

### `GET /health`

无需鉴权。

| 字段 | 说明 |
| --- | --- |
| `status` | `ok` / `degraded` |
| `apps` | 已注册 `app_key` 列表 |
| `services` | `service_key → health_check` |

## 2. 应用 `auth`（`app_key=auth`）

### `POST /api/v1/auth/login`

请求：`{"username", "password"}`。响应：`TokenPairResponse`（`access_token` / `refresh_token` / `expires_in` / `token_type=Bearer`）。失败 `401`：`invalid_credentials` / `user_disabled`。

### `POST /api/v1/auth/refresh`

请求：`{"refresh_token"}`。响应同登录。重用已吊销 refresh：`401 refresh_reuse`。

### `POST /api/v1/auth/logout`

需 access。请求：`{"refresh_token": string | null}`。将当前 access `jti` 写入 Redis 黑名单，可选吊销 refresh。

### `GET /api/v1/auth/me`

需 access。响应：`id` / `username` / `organization_id` / `roles`。

缺少 Token：`401 token_missing`。

## 3. 应用 `conversation`（`app_key=conversation`）

会话归属当前用户；越权 `403 conversation_forbidden`，不存在 `404 conversation_not_found`。

### `GET /api/v1/conversations`

查询：`offset` / `limit`。响应：会话数组（`id` / `user_id` / `title` / `app_key` / `flow_id` / `status`）。

### `POST /api/v1/conversations`

请求：`title` / `flow_id` / `metadata` 均可空。

### `GET /api/v1/conversations/{conversation_id}`

### `GET /api/v1/conversations/{conversation_id}/messages`

查询：`offset` / `limit`。响应消息：`role` / `content_blocks` / `status`。

### `POST /api/v1/conversations/messages`

对齐 `SendMessageRequest` / `SendMessageResponse`。

请求：

| 字段 | 说明 |
| --- | --- |
| `conversation_id` | 空则新建会话 |
| `app_key` | 默认 `conversation` |
| `flow_id` | 与会话上的 `flow_id` 至少一个非空 |
| `content` | 用户文本 |
| `metadata` | 可选 |

同一请求内写入 user Message（`completed`）与 assistant Message（`streaming`），再调用 `WorkflowRuntimeService.start`（本轮测试可注入 Fake，不入队真实图）。随后向进程内总线发布 `run_submitted`。缺少 `flow_id`：`400 flow_id_required`。

响应：`conversation_id` / `user_message_id` / `assistant_message_id` / `run_id`（不写会话表外键）。

### `GET /api/v1/conversations/{conversation_id}/events`

`Content-Type: text/event-stream`。连接后状态机 `subscribe`，首帧 `connected`。服务层对 `ff.stream` 做 MQ subscribe，帧进入该连接有界 `asyncio.Queue`，生成器只消费 Queue。约 15s 无事件发送 keepalive。`speaking` 可从 `subscribed` 直接进入 `run_active`（避免丢失 `run_submitted`）。

## 4. SSE 流协议状态机

状态：`idle` → `subscribed` → `run_active` → `completed` | `failed`。`completed` / `failed` 可再次 `run_submitted` 进入下一轮。任意时刻 `unsubscribe` 回到 `idle`。

| 事件 | 合法源状态 | 说明 |
| --- | --- | --- |
| `connected` | 仅由 `subscribe` 产生 | `data.state` |
| `run_submitted` | subscribed / completed / failed | `data.run_id` / `message_id` |
| `speaking` / `reasoning` / `tool_calling` / `step_running` / `subagent_running` | subscribed 或 run_active | worker 流式出词走 `speaking`；token 不经护栏 |
| `run_completed` / `run_failed` | run_active | 控制事件 |

非法转移：状态机抛出 `StreamProtocolError`；SSE 连接上记录 warning 并丢弃该帧，不断开。

SSE 文本格式：

```text
event: <name>
id: <seq>
data: <json>

```

`id` 由状态机递增，便于后续 Last-Event-ID。

## 5. 本轮未暴露

知识入库/检索、Flow/Agent CRUD、HITL、用户角色管理、限流、流式 token 级护栏。
