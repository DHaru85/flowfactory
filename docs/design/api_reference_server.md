# FLowFactory 后端服务API说明文档

本文描述 **应用层接口**（FastAPI），含 `auth` / `conversation` / `studio` / `models` / `agent_config`。服务层能力见 [service_layer.md](./service_layer.md)；表结构见 [data_schema_server.md](./data_schema_server.md)。未开工轮次见 [plan/unreached](../plan/unreached/)。

- 基址前缀：`/api/v1`（健康检查除外）。
- 鉴权：除登录、注册、刷新、`GET /health` 外，请求头 `Authorization: Bearer <access_token>`。业务应用另需 **应用绑定或角色 grant**（见下）。
- 错误体：`{"code": string, "message": string}`。无权进入应用：`403 app_forbidden`。
- RBAC：平台管理员 = `sys_user.is_superuser`（与 RBAC 管理员同一角色定义），天生可查看/修改/删除全部应用与资源配置。非超管分两档：**可见可用**（`read`/`use`，`write`/`admin` 亦算可见）与 **修改与完全控制**（`write`/`admin`）。应用可见性由 `agent_resource_binding`（`resource_type=application`）与 `PermissionService` 角色 grant **并集**决定；组织不沿父级继承。`GET /health` 的 `apps` 不过滤。
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

### `POST /api/v1/auth/register`

无需鉴权。请求：`{"username", "password"(≥8), "display_name"?}`。`display_name` 空则等于用户名。保证存在组织 `code=default`；库中尚无未删除用户时该账号为超管。响应同登录 `TokenPairResponse`。用户名冲突：`409 username_conflict`。

### `POST /api/v1/auth/login`

请求：`{"username", "password"}`。响应：`TokenPairResponse`（`access_token` / `refresh_token` / `expires_in` / `token_type=Bearer`）。失败 `401`：`invalid_credentials` / `user_disabled`。

### `POST /api/v1/auth/refresh`

请求：`{"refresh_token"}`。响应同登录。重用已吊销 refresh：`401 refresh_reuse`。

### `POST /api/v1/auth/logout`

需 access。请求：`{"refresh_token": string | null}`。将当前 access `jti` 写入 Redis 黑名单，可选吊销 refresh。

### `GET /api/v1/auth/me`

需 access。响应：`id` / `username` / `organization_id` / `roles`。

缺少 Token：`401 token_missing`。

### `GET /api/v1/auth/apps`

需 access。返回当前用户可见应用：`app_key` / `name` / `can_use` / `can_control`。`auth` 对已登录用户始终出现。超管 `can_control` 为全部已注册应用。

### `GET /api/v1/auth/apps/{app_key}/bindings`

### `PUT /api/v1/auth/apps/{app_key}/bindings`

仅超管。覆盖写入该应用对组织/部门/角色/个人的绑定。未知应用 `404 app_not_found`。主体不存在 `400 subject_not_found`。

## 3. 应用 `conversation`（注册 `app_key=conversation`）

需对 `conversation` **可见可用** 才能列表/详情/SSE；**完全控制** 才能建会话、发消息。会话归属当前用户；越权 `403 conversation_forbidden`，不存在或**跨场景前缀** `404 conversation_not_found`。规划与工作流共用 `conv_*` 表与 SSE 协议，HTTP 分路径。列表项不含 `metadata`；详情含 `metadata`。规划所用 Profile 须对当前用户资源可见，否则 `404 profile_not_found`。

会话行 `app_key`：规划为 `planner`；`/workflow*` 新建为 `workflow`；兼容路径新建为 `conversation`。`/workflow*` 与兼容路径列表过滤 `app_key in (workflow, conversation)`。

规划智能体 `profile_id` 只写入 `metadata.profile_id`，不占用 `flow_id`。

### 规划路径 `/api/v1/conversations/planner*`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/planner` | 仅当前用户 planner 会话；列表无 `profile_id` |
| POST | `/planner` | 必填 `profile_id`；Profile 不存在 `400 profile_not_found` |
| GET | `/planner/{id}` | 详情含 `metadata.profile_id` |
| GET | `/planner/{id}/messages` | 消息列表 |
| POST | `/planner/messages` | 校验会话与 Profile 后入队规划 Run，返回 `run_id`；`kind=planner` |
| GET | `/planner/{id}/events` | SSE，协议同工作流 |

`POST /planner/messages`：`profile_id` 可省略（从会话 metadata 继承）；二者皆空 `400 profile_id_required`。写入 user / assistant（streaming）后入队 `kind=planner` 的 Run，返回 `run_id`。规划循环见服务层 `PlannerRuntime`。

### 工作流路径 `/api/v1/conversations/workflow*`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/workflow` | 创建可带 `flow_id`；`app_key=workflow` |
| GET | `/workflow/hitl-pendings` | 属主或超管的 pending HITL；可选 `run_id` |
| GET | `/workflow/hitl-pendings/{hitl_id}` | 越权 `404 hitl_not_found` |
| POST | `/workflow/hitl-pendings/{hitl_id}/resume` | `decision` + 可选 `user_input`；非 pending `400 hitl_not_resumable` |
| GET | `/workflow/{id}` | 详情含 `metadata` |
| GET | `/workflow/{id}/messages` | 消息列表 |
| POST | `/workflow/messages` | 与下方兼容发消息相同，新建会话 `app_key=workflow` |
| GET | `/workflow/{id}/events` | SSE |

### 兼容别名 `/api/v1/conversations`（无中间段）

行为与 `/workflow*` 相同，供既有客户端。`POST /conversations` 仍写 `app_key=conversation`。

### `GET /api/v1/conversations` 与 `/workflow`、`/planner`

查询：`offset` / `limit`。响应列表：`id` / `user_id` / `title` / `app_key` / `flow_id` / `status`（无 `metadata`）。

### `POST /api/v1/conversations/messages`（及 `/workflow/messages`）

对齐 `SendMessageRequest` / `SendMessageResponse`。

请求：

| 字段 | 说明 |
| --- | --- |
| `conversation_id` | 空则新建会话 |
| `app_key` | 兼容路径默认 `conversation`；仅当值为 `workflow` 或 `conversation` 时用于新建 |
| `flow_id` | 与会话上的 `flow_id` 至少一个非空 |
| `content` | 用户文本 |
| `metadata` | 可选 |

同一请求内写入 user Message（`completed`）与 assistant Message（`streaming`），再调用 `WorkflowRuntimeService.start`。随后经 `get_stream_bus()` 发布 `run_submitted`（有 `FLOWFACTORY_RABBITMQ_URL` 时走 `ff.stream`）。缺少 `flow_id`：`400 flow_id_required`。

响应：`conversation_id` / `user_message_id` / `assistant_message_id` / `run_id`（不写会话表外键）。

### SSE

`GET .../{conversation_id}/events`（三套前缀）。`Content-Type: text/event-stream`。连接后状态机 `subscribe`，首帧 `connected`。服务层对 `ff.stream` 做 MQ subscribe，帧进入该连接有界 `asyncio.Queue`，生成器只消费 Queue。约 15s 无事件发送 keepalive。`speaking` 可从 `subscribed` 直接进入 `run_active`（避免丢失 `run_submitted`）。

## 4. SSE 流协议状态机

状态：`idle` → `subscribed` → `run_active` → `completed` | `failed`。`completed` / `failed` 可再次 `run_submitted` 进入下一轮。任意时刻 `unsubscribe` 回到 `idle`。

| 事件 | 合法源状态 | 说明 |
| --- | --- | --- |
| `connected` | 仅由 `subscribe` 产生 | `data.state` |
| `run_submitted` | subscribed / completed / failed | `data.run_id` / `message_id` |
| `speaking` / `reasoning` / `tool_calling` / `step_running` / `subagent_running` / `run_interrupted` | subscribed 或 run_active | `run_interrupted` 保持 run_active，`data.hitl_id` / `node_id` / `prompt` |
| `run_completed` / `run_failed` | run_active | 控制事件 |

非法转移：状态机抛出 `StreamProtocolError`；SSE 连接上记录 warning 并丢弃该帧，不断开。

SSE 文本格式：

```text
event: <name>
id: <seq>
data: <json>

```

`id` 由状态机递增，便于后续 Last-Event-ID。

## 5. 应用 `studio`（`app_key=studio`）

工作流编排配置态。需对 `studio` 可见可用（列表/详情/目录）或完全控制（草稿/发布/新草稿）。无权限 `403 app_forbidden`。`schema_version=1` 图经 `FlowRuntime.compile` 双读后可被 `WorkflowRuntimeService.start` / 会话入队执行。v0 内联 definition 仍可用。Profile/Tool 目录再按资源绑定过滤；LLM 目录无行级绑定。

非法图：`400 definition_invalid`。非草稿修改：`400 flow_not_draft`。不存在：`404 flow_not_found`。`code+version` 冲突：`409 flow_code_version_conflict`。

### `GET /api/v1/studio/profiles`

只读。`id` / `code` / `name`。

### `GET /api/v1/studio/llms`

只读，仅 `is_active`。不下发 `config`。

### `GET /api/v1/studio/tools`

只读。`code` / `name` / `kind`。本轮不做工具写与规划循环。

### `GET /api/v1/studio/flows/published-codes`

已发布 `code` + 最大 `version`。

### `GET /api/v1/studio/flows`

查询：`offset` / `limit` / `status` / `code`。列表跳过非 v1 行。

### `POST /api/v1/studio/flows`

`code` / `name` / `profile_id`；`definition` 可空（写入 start→end 空图）。`profile_id` 无效：`400 profile_not_found`。

### `GET /api/v1/studio/flows/{flow_id}`

非 v1：`400 flow_definition_not_v1`。

### `PATCH /api/v1/studio/flows/{flow_id}`

仅 `draft`。

### `POST /api/v1/studio/flows/{flow_id}/publish`

同 `code` 其它 `published` 改为 `archived`。子图 `flow_code` 必须已发布且无 code 级环。

### `POST /api/v1/studio/flows/{flow_id}/new-draft`

仅 `published`。复制为 `version+1` 的 draft。

## 6. 应用 `models`（`app_key=models`）

公共 LLM 目录。需对 `models` 可见可用（列表/详情）或完全控制（创建/PATCH/停用）。密钥不出现在响应 JSON 的 `config` 中；以 `has_api_key` 表示是否已配置。`provider`：`openai` / `azure` / `local`。非法 provider：`400 provider_invalid`。code 冲突：`409 llm_code_conflict`。不存在：`404 llm_not_found`。无行级绑定。

Studio `GET /api/v1/studio/llms` 仍只读活跃项、不下发 `config`。运行时 `resolve_llm_client` 按 `agent_llm` 装配客户端，缺省回退环境变量 `llm_*`。

规划循环、会话路径拆分已落地。RBAC 见本文开头与 `agent_config` 绑定规则。

### `GET /api/v1/models/llms`

查询：`offset` / `limit` / `is_active`（可选）。

### `POST /api/v1/models/llms`

`code` / `provider` / `model_name` / `config` / `is_active`。

### `GET /api/v1/models/llms/{id}`

### `PATCH /api/v1/models/llms/{id}`

`config.api_key` 省略或空字符串表示不覆盖已有密钥。

### `POST /api/v1/models/llms/{id}/deactivate`

`is_active=false`。

## 7. 应用 `agent_config`（`app_key=agent_config`）

Profile / Skill / Tool / MCP / Beat（工作流或规划）。需对 `agent_config` 可见可用或完全控制。创建配置资源时登记 `sys_asset`。绑定 `PUT .../bindings` 仅完全控制（或超管）覆盖写入 `agent_resource_binding`，主体须存在否则 `400 subject_not_found`。

普通人列表/详情仅命中自身组织/部门/角色/用户绑定且 actions 含 `read`/`use`/`write`/`admin` 的资源；未绑定不可见；越权详情 `404`（不 `403`）。完全控制者与超管可见该应用全部配置（含未绑定）。Beat 无行级绑定：可见可用即可列表/详情，完全控制才能创建/改/启停。

code 冲突 `409`。缺引用 `400`（`llm_not_found` / `skill_not_found` / `tool_not_found` / `mcp_server_not_found` / `flow_not_found` / `profile_not_found` / `mcp_server_required`）。非法 cron：`400 cron_invalid`。

### Profile

`GET/POST /api/v1/agent-config/profiles`，`GET/PATCH /api/v1/agent-config/profiles/{id}`，`GET/PUT /api/v1/agent-config/profiles/{id}/bindings`。

字段：`code` / `name` / `system_prompt` / `default_llm_id` / `skill_ids`。不按 `owner_organization_id` 过滤。

### Skill

`GET/POST /api/v1/agent-config/skills`，`GET/PATCH .../skills/{id}`，`GET/PUT .../skills/{id}/bindings`。

### Tool

`GET/POST /api/v1/agent-config/tools`，`GET/PATCH .../tools/{id}`，`GET/PUT .../tools/{id}/bindings`。`kind=mcp` 必须 `mcp_server_id`。

### MCP Server

`GET/POST /api/v1/agent-config/mcp-servers`，`GET/PATCH .../mcp-servers/{id}`，`GET/PUT .../mcp-servers/{id}/bindings`。本轮不探测连通。`transport`：`stdio` / `sse`。

### Beat（工作流或规划）

`GET/POST /api/v1/agent-config/beat-tasks`，`GET/PATCH .../beat-tasks/{id}`，`POST .../beat-tasks/{id}/enable`，`POST .../beat-tasks/{id}/disable`。

创建时 `flow_id` 与 `profile_id` 恰一：只传 `flow_id` 为工作流定时（第 1 轮契约）；只传 `profile_id` 为规划定时。皆空 `400 beat_target_required`；皆有 `400 beat_target_conflict`。响应含可空 `profile_id`。PATCH 只改 `cron` / `input_payload`。

到期：工作流走 Flow compile；规划 `kind=planner` 入队，不 compile Flow。系统用户未配置则跳过。

### 应用与资源绑定

应用绑定：`PUT /api/v1/auth/apps/{app_key}/bindings`。配置绑定：`GET/PUT /api/v1/agent-config/{profiles|skills|tools|mcp-servers}/{id}/bindings`。
