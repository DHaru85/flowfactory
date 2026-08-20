# FlowFactory 表示层数据结构设计说明

本文档按**功能领域**（二级标题）分区，整理 React 工程应对接的数据结构。服务端表与进程内对象见 [data_schema_server.md](./data_schema_server.md)；HTTP / SSE 契约见 [api_reference_server.md](./api_reference_server.md)。字段以现网 JSON 为准（`src/backend/api/apps/*/schemas.py`、SSE 协议），不以 ORM 列全集为准。

后续 TypeScript 落点建议：`src/frontend/source/types/` 按域拆文件。本轮只定义契约，不创建前端工程。

## 分类说明

| 分类 | 对应服务端 | 含义 | 典型落点 |
| --- | --- | --- | --- |
| **传输对象** | 序列化对象（HTTP/SSE 子集） | 请求体、响应体、SSE `data` JSON；字段名与线上一致 | Axios 泛型、`EventSource` 解析 |
| **可运行对象** | 可运行对象（浏览器侧） | 可实例化、有生命周期，调度 UI 与网络；**不**落 IndexedDB 表、**不**镜像 Celery/LDAP | 鉴权会话、SSE 订阅、画布编辑会话 |
| **视图模型** | （服务端无对应） | 仅 UI 需要的派生态；由传输对象 + 可运行对象归并 | 流式消息缓冲、侧栏应用列表、画布选中集 |

**补充约定**

- 授权真相以服务端 `AccessControl` 为准。前端用 `GET /auth/apps` 的 `can_use` / `can_control` 与各接口 403/404 驱动 UI，**不**把 JWT payload 当授权源（`/me` 不含 `is_superuser`）。
- 列表现网为**裸数组** + 查询参数 `offset` / `limit`，无 `{ items, total }` 信封。
- 密钥、密码摘要、Redis key、Celery 信封、checkpointer 字节**永不进入**传输对象或视图模型。
- 尚无应用层 HTTP 的域保留空章（三类标题 +「待补」），开放接口后再填字段表。

### 标量映射

| 服务端 | 客户端 TypeScript | JSON 形态 |
| --- | --- | --- |
| UUID | `string` | 标准 UUID 文本 |
| datetime / TIMESTAMPTZ | `string` | ISO 8601 |
| bool / int / str | `boolean` / `number` / `string` | 同 JSON |
| JSONB / dict | 能收窄则联合类型，否则 `Record<string, unknown>` | 对象 |
| 枚举 VARCHAR | 字符串字面量联合 | 与 API 文档一致 |

### 鉴权头与基址

- 基址前缀：`/api/v1`（`GET /health` 除外）。
- 除登录、刷新、健康检查外：`Authorization: Bearer <access_token>`。
- 业务应用另需应用绑定或角色 grant；无权：`403`，`code=app_forbidden`。

---

## 通用传输对象

跨域复用，不单独对应一个 Application。

### 传输对象

#### Error Body

对应 Python `ErrorBody`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `string` | 稳定错误码，如 `invalid_credentials`、`app_forbidden` |
| `message` | `string` | 可读说明 |

HTTP 状态与 `code` 对照以 [api_reference_server.md](./api_reference_server.md) 为准。Axios 拦截器对 `401` / `403` 统一处理（刷新或跳转登录、隐藏无权限入口）。

#### Offset Limit Query

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `offset` | `number` | 默认 `0` |
| `limit` | `number` | 会话列表默认 `50`（服务端上限 100）；消息列表默认 `100`（上限 200）；其它列表常见默认 `50`（上限 100） |

#### Status Ok

`POST /auth/logout` 等无业务载荷的成功体。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | `"ok"` | |

### 可运行对象

#### Http Client

##### 类 `HttpClient`（约定，未实现）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `baseUrl` | `string` | API 根 |
| `auth` | `AuthSession` | 注入 Bearer；401 触发 refresh |

不规定必须 Axios；禁止 Vercel AI SDK。

### 视图模型

（无独立通用视图；各域自行组合。）

---

## 健康检查

### 传输对象

#### Health Out

对应 `GET /health`。无需鉴权。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | `"ok" \| "degraded"` | 全部已注册 Service `health_check` 为真则为 `ok` |
| `apps` | `string[]` | 已注册 `app_key`，**不过滤**当前用户可见性 |
| `services` | `Record<string, boolean>` | `service_key → health_check` |

### 可运行对象

（无。运维探针，SPA 可不调用。）

### 视图模型

（待补。若做状态页再定义。）

---

## Permission Manage（鉴权与应用可见性）

对应服务端 Permission 域中**已开放**的 HTTP。组织树、角色、配额、LDAP 作业、刷新令牌表见本章末「未开放管理面」及后文空章交叉引用。

### 传输对象

#### Login Body

对应 `LoginBody` / `POST /api/v1/auth/login`。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `username` | `string` | 1–64 | 登录名 |
| `password` | `string` | min 1 | 仅 TLS 传输，不入库、不进视图模型 |

#### Register Body

对应 `RegisterBody` / `POST /api/v1/auth/register`。无需 Token。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `username` | `string` | 1–64 | 登录名 |
| `password` | `string` | 8–128 | 仅 TLS |
| `display_name` | `string \| null` | 最大 128 | 空则等于用户名 |

成功响应为 `TokenPair`。冲突：`409 username_conflict`。首位未删除用户为超管，加入 `default` 组织。

#### Refresh Body

对应 `RefreshBody` / `POST /api/v1/auth/refresh`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `refresh_token` | `string` | 客户端持有的 refresh |

#### Logout Body

对应 `LogoutBody` / `POST /api/v1/auth/logout`。需 access。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `refresh_token` | `string \| null` | `null` 则仅吊销当前 access `jti` |

#### Token Pair

对应 `TokenPairResponse`。登录与刷新响应相同。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `access_token` | `string` | 短 JWT |
| `refresh_token` | `string` | opaque 或 JWT refresh |
| `expires_in` | `number` | access 有效秒数 |
| `token_type` | `"Bearer"` | 固定 |

失败：`401` `invalid_credentials` / `user_disabled`；刷新重用：`401` `refresh_reuse`。缺 Token：`401` `token_missing`。

#### Me Out

对应 `GET /api/v1/auth/me`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | 用户 id |
| `username` | `string` | |
| `organization_id` | `string (UUID)` | 当前组织 |
| `roles` | `string[]` | 角色 **code** 列表 |

不含 `is_superuser`、`email`、`display_name`。展示名若需要，待用户资料 API。

#### App Visibility Out

对应 `GET /api/v1/auth/apps`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `app_key` | `string` | 如 `auth` / `conversation` / `studio` / `models` / `agent_config` |
| `name` | `string` | 展示名 |
| `can_use` | `boolean` | 可见可用（列表/详情/只读目录） |
| `can_control` | `boolean` | 修改与完全控制 |

`auth` 对已登录用户始终出现。侧栏只渲染本列表，不要用 `/health.apps` 当菜单。

#### Binding Item

对应 `BindingItem`。应用绑定与配置资源绑定共用。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `subject_type` | `"organization" \| "department" \| "role" \| "user"` | 主体类型 |
| `subject_id` | `string (UUID)` | 主体 id |
| `actions` | `string[]` | 默认 `["read","use"]`；完全控制含 `write` / `admin` |

#### Binding Put Body

对应 `BindingPutBody`。覆盖写入。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `bindings` | `BindingItem[]` | 全量替换 |

`GET/PUT /api/v1/auth/apps/{app_key}/bindings`：仅平台管理员（`is_superuser`）。未知应用 `404 app_not_found`；主体不存在 `400 subject_not_found`。配置资源绑定路径见 Agent 配置域。

### 可运行对象

#### Auth Session

##### 类 `AuthSession`（约定）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `accessToken` | `string \| null` | 内存持有；注入 HttpClient |
| `refreshToken` | `string \| null` | 刷新用 |
| `expiresAt` | `number \| null` | 由 `expires_in` 推算的 epoch 秒 |
| `me` | `MeOut \| null` | 登录后拉取 |

##### 运行方法（约定）

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `login` | `LoginBody` | `TokenPair` | 写入 token 后 `GET /me` |
| `refresh` | — | `TokenPair` | 使用 `refreshToken` |
| `logout` | — | — | `POST /logout` 后清空 |
| `loadMe` | — | `MeOut` | |

持久化（localStorage 等）可选；若持久化 refresh，需接受 XSS 风险，不在本文强制。禁止把 `password` 存入本对象。

### 视图模型

#### App Shell Menu

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | `AppVisibilityOut[]` | 来自 `/auth/apps` |
| `currentAppKey` | `string \| null` | 当前路由对应应用 |

写操作按钮：`can_control === true` 才展示。

### 未开放管理面（空节）

组织、部门、角色、Assets 管理、配额、LDAP 同步作业、外部身份映射、用户 CRUD **无公开 HTTP**。字段待补；服务端见 `data_schema_server.md` Permission 章。前端不得假设能读 `password_hash`、`sys_refresh_token`、JWT 黑名单 Redis。

---

## Application and Service Registry

应用/服务组合在后端 Python 注册，**不落绑定表**。浏览器不持有 Registry 实例。

### 传输对象

可见应用列表见上节 `AppVisibilityOut`。注册表本身无独立 CRUD API。

（待补：若开放 `GET /apps` 管理面再填。）

### 可运行对象

（无。禁止在前端维护 `app_key → Application` 镜像表。）

### 视图模型

（无。菜单用 `App Shell Menu`。）

---

## Conversation and Session SSE Protocol

规划与工作流共用 `conv_*` 与 SSE；HTTP 分路径。会话归属当前用户。

- 列表/详情/SSE：对 `conversation` **可见可用**。
- 建会话、发消息：**完全控制**。
- 越权 `403 conversation_forbidden`；不存在或跨场景前缀 `404 conversation_not_found`。

`app_key`：规划 `planner`；`/workflow*` 新建 `workflow`；兼容路径新建 `conversation`。`/workflow*` 与兼容列表过滤 `app_key in ("workflow","conversation")`。

规划 `profile_id` 只在详情 `metadata.profile_id`（UUID 字符串），不占用 `flow_id`。列表项无 `metadata`。

### 传输对象

#### Conversation Create Body

对应 `ConversationCreateBody`。`POST .../workflow` 与兼容 `POST /conversations`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | `string \| null` | 最大 256 |
| `flow_id` | `string (UUID) \| null` | 工作流会话可带 |
| `metadata` | `Record<string, unknown> \| null` | |

#### Planner Conversation Create Body

对应 `PlannerConversationCreateBody`。`POST /api/v1/conversations/planner`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | `string \| null` | |
| `profile_id` | `string (UUID)` | 必填；Profile 对当前用户不可见则 `404 profile_not_found`；不存在 `400 profile_not_found` |
| `metadata` | `Record<string, unknown> \| null` | 服务端会写入 `profile_id` |

#### Conversation Out

对应 `ConversationOut`（列表）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `user_id` | `string (UUID)` | |
| `title` | `string \| null` | |
| `app_key` | `string` | `planner` / `workflow` / `conversation` |
| `flow_id` | `string (UUID) \| null` | 规划会话为空 |
| `status` | `"active" \| "archived" \| "deleted"` | 与表约定一致 |

#### Conversation Detail Out

对应 `ConversationDetailOut`。列表字段 +：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `metadata` | `Record<string, unknown>` | 规划含 `profile_id` |

#### Message Out

对应 `MessageOut`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `conversation_id` | `string (UUID)` | |
| `role` | `"user" \| "assistant" \| "system" \| "tool"` | |
| `content_blocks` | `MessageContentBlock[]` | 现网 JSON 为对象数组 |
| `status` | `"streaming" \| "completed" \| "failed" \| "cancelled"` | |

现网列表响应未含 `token_usage` / 时间戳；UI 不以未下发字段为准。

#### Message Content Block

判别联合，`type` 为判别字段。与服务端 `MessageContentBlock` 对齐。

| 变体 | 字段 | 说明 |
| --- | --- | --- |
| `type=text` | `text: string` | 纯文本 |
| `type=reasoning` | `text: string` | 推理块 |
| `type=tool_call` | `tool_call_id`, `name`, `arguments`, `result?` | 工具调用 |
| `type=artifact` | `mime_type`, `url`, `metadata` | 产物引用 |

发消息时服务端将用户输入写成 `[{ type: "text", text }]`；assistant 初始 `content_blocks=[]`，`status=streaming`。

#### Send Message Body

对应 `SendMessageBody`。`POST /conversations/messages` 与 `/workflow/messages`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | `string (UUID) \| null` | 空则新建 |
| `app_key` | `string` | 兼容路径默认 `conversation`；新建仅当 `workflow` 或 `conversation` |
| `flow_id` | `string (UUID) \| null` | 与会话上 `flow_id` 至少一个非空，否则 `400 flow_id_required` |
| `content` | `string` | min 1 |
| `metadata` | `Record<string, unknown> \| null` | |

#### Planner Send Message Body

对应 `PlannerSendMessageBody`。`POST /conversations/planner/messages`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | `string (UUID) \| null` | |
| `profile_id` | `string (UUID) \| null` | 可省略，从会话 metadata 继承；皆空 `400 profile_id_required` |
| `content` | `string` | min 1 |
| `metadata` | `Record<string, unknown> \| null` | |

#### Send Message Out

对应 `SendMessageOut`。`run_id` **不**写入会话表外键。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | `string (UUID)` | |
| `user_message_id` | `string (UUID)` | 已落库 user |
| `assistant_message_id` | `string (UUID)` | 预创建 streaming assistant |
| `run_id` | `string (UUID)` | 已提交 Run |

#### SSE Frame

对应 `StreamEvent`。文本格式：

```text
event: <name>
id: <seq>
data: <json>

```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | `SseEventName` | SSE `event:` |
| `id` | `string \| null` | 状态机递增，供后续 Last-Event-ID |
| `data` | 见下表 | JSON |

`SseEventName`：`connected` | `run_submitted` | `speaking` | `reasoning` | `tool_calling` | `step_running` | `subagent_running` | `run_completed` | `run_failed`。

约 15s 无业务事件会发 keepalive（注释行或空注释，以实现为准）；客户端忽略，不驱动状态机。

##### connected

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.state` | `"subscribed"` | 连接后首帧 |

##### run_submitted

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.run_id` | `string (UUID)` | |
| `data.message_id` | `string (UUID)` | assistant 消息 |

##### speaking / reasoning

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.delta` | `string` | 增量文本 |
| `data.message_id` | `string (UUID)` | |

`speaking` **不经内容护栏**。

##### tool_calling

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.tool_call_id` | `string` | |
| `data.tool_name` | `string` | |
| `data.arguments` | `Record<string, unknown>` | |
| `data.status` | `"started" \| "completed" \| "failed"` | |
| `data.result` | `unknown` | 完成时可选 |

##### step_running

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.node_id` | `string` | |
| `data.step_name` | `string` | |
| `data.status` | `"started" \| "completed" \| "failed"` | |

##### subagent_running

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.subagent_key` | `string` | |
| `data.status` | `"started" \| "completed"` | |
| `data.summary` | `string \| null` | |

##### run_completed / run_failed

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.run_id` | `string (UUID)` | |

### 可运行对象

#### Conversation Sse Client

##### 类 `ConversationSseClient`（约定）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `conversationId` | `string` | |
| `scene` | `"planner" \| "workflow"` | 决定 URL 前缀 |
| `state` | `SseClientState` | 镜像服务端状态机 |
| `lastEventId` | `string \| null` | 重连预留 |

`SseClientState`：`idle` | `subscribed` | `run_active` | `completed` | `failed`。

路径：`GET /api/v1/conversations/planner/{id}/events` 或 `/workflow/{id}/events`（兼容 `/conversations/{id}/events`）。`Content-Type: text/event-stream`。须带 Bearer（实现可用 fetch stream；原生 `EventSource` 不能自定义头时需另议，不在本轮强制）。

##### 运行方法（约定）

| 方法 | 说明 |
| --- | --- |
| `subscribe()` | 打开连接；首帧 `connected` → `subscribed` |
| `unsubscribe()` | 关闭；回 `idle` |
| `onFrame(frame)` | 合法转移才更新 `state`；非法帧丢弃不断开（与服务端一致） |

合法转移：`idle`→`subscribed`（connected）；`subscribed`/`completed`/`failed`→`run_active`（`run_submitted`）；`speaking` 等 delta 可从 `subscribed` 直接进入 `run_active`；`run_completed`/`run_failed` 仅 `run_active`。完成后可再 `run_submitted` 进入下一轮。

### 视图模型

#### Streaming Message View

按 `assistant_message_id` / SSE `message_id` 归并。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messageId` | `string` | |
| `role` | `MessageOut["role"]` | |
| `status` | `MessageOut["status"]` | 流中为 `streaming` |
| `text` | `string` | `speaking` delta 拼接 |
| `reasoning` | `string` | `reasoning` delta 拼接 |
| `toolCalls` | 按 `tool_call_id` 的映射 | 更新 `status`/`result` |
| `steps` | `step_running[]` | 时间线展示 |
| `runId` | `string \| null` | 本轮 Run |

历史消息用 `MessageOut.content_blocks` 渲染；流式以本视图覆盖同一 `messageId`，`run_completed` 后可再拉消息列表校准。

#### Conversation List Item View

直接使用 `ConversationOut`。规划列表**不要**读 `profile_id`（未下发）；进详情再读 `metadata`。

---

## Agent Configuration and Workflow Definitions（Studio 画布 + 配置目录）

Studio（`app_key=studio`）管 Flow 草稿/发布与只读目录；完整 Profile/Skill/Tool/MCP/Beat CRUD 在 `agent_config`。图文档 `schema_version=1` 两端共用。`compile` **必须忽略** `view`；画布坐标只写 `view`。

Studio：可见可用 → 列表/详情/目录；完全控制 → 草稿/发布/新草稿。非法图 `400 definition_invalid`；非草稿修改 `400 flow_not_draft`；非 v1 详情 `400 flow_definition_not_v1`；`409 flow_code_version_conflict`。

列表跳过非 v1 行。v0 松散 dict **不进入**客户端编辑器。

### 传输对象

#### Profile Catalog Out

`GET /api/v1/studio/profiles`。再按资源绑定过滤。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `code` | `string` | |
| `name` | `string` | |

#### Llm Catalog Out

`GET /api/v1/studio/llms`。仅 `is_active`；**不下发** `config`。LLM **无行级绑定**。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `code` | `string` | |
| `provider` | `string` | |
| `model_name` | `string` | |

#### Tool Catalog Out

`GET /api/v1/studio/tools`。按资源绑定过滤。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `code` | `string` | |
| `name` | `string` | |
| `kind` | `string` | `builtin` / `http` / `mcp` |

#### Published Flow Code Out

`GET /api/v1/studio/flows/published-codes`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `string` | |
| `version` | `number` | 该 code 当前最大已发布版本 |

#### Flow Create Body

`POST /api/v1/studio/flows`。`profile_id` 无效 `400 profile_not_found`。`definition` 空则服务端写入 start→end 空图。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `string` | 1–64 |
| `name` | `string` | 1–128 |
| `profile_id` | `string (UUID)` | |
| `definition` | `FlowDefinitionV1 \| null` | 可空 |

#### Flow Patch Body

仅 `draft`。`PATCH /api/v1/studio/flows/{flow_id}`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `string \| null` | |
| `profile_id` | `string (UUID) \| null` | |
| `definition` | `FlowDefinitionV1 \| null` | |

#### Flow Out

详情/创建/发布后的主体。列表项现网同结构含 `definition`（以路由 `response_model` 为准）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `code` | `string` | |
| `name` | `string` | |
| `version` | `number` | |
| `profile_id` | `string (UUID)` | |
| `status` | `"draft" \| "published" \| "archived"` | |
| `published_at` | `string \| null` | ISO 8601 |
| `definition` | `FlowDefinitionV1` | |

`POST .../publish`：同 `code` 其它 `published` 改为 `archived`。`POST .../new-draft`：仅 `published`，复制为 `version+1` 的 draft。子图 `flow_code` 必须已发布且无 code 级环。

查询列表：`offset` / `limit` / `status` / `code`。

#### Flow Definition V1

对应 `FlowDefinitionV1`。`schema_version` 固定 `1`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | `1` | |
| `state` | `GraphStateSpec` | 三槽声明，不含一次运行的值 |
| `nodes` | `FlowNode[]` | 恰一个 `start`，至少一个 `end` |
| `edges` | `FlowEdge[]` | 无条件边 |
| `branches` | `FlowBranch[]` | 条件扇出 |
| `view` | `FlowView \| null` | 仅画布 |

拓扑只在边与分支上。`entry_point` / `interrupt_before` 不是作者字段。禁止在 JSON 内嵌可执行代码。

#### Graph State Spec

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `channels` | `StateChannelSpec[]` | **恰好三条** |

#### State Channel Spec

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `"messages" \| "variables" \| "metadata"` | 不可增删顶层槽 |
| `reducer` | `"append" \| "merge"` | `messages` 必须 `append`；另两槽必须 `merge` |
| `json_schema` | `Record<string, unknown> \| null` | 仅 `variables` 可填，约束内层键 |

#### Flow Node

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | 文档内唯一 |
| `type` | `NodeType` | discriminator |
| `title` | `string \| null` | 仅展示 |
| `data` | 随 `type` | 禁止裸 `string` |

`NodeType`：`start` | `end` | `llm` | `tool` | `assign` | `hitl` | `subgraph` | `custom`。

#### Start Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `inject` | `InjectSpec[]` | 运行时写入哪条通道 |

#### Inject Spec

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source` | `"run" \| "user" \| "conversation" \| "beat" \| "clock"` | |
| `channel` | `"messages" \| "variables" \| "metadata"` | |
| `key` | `string \| null` | 写 `messages` 时为空 |

#### End Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `output_channels` | `("messages" \| "variables" \| "metadata")[]` | 写入本 Run `output_payload` 的槽 |

#### Llm Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `llm_ref` | `string` | `agent_llm.code` |
| `system_prompt` | `string \| null` | 覆盖 Profile |
| `stream` | `boolean` | 默认 `true` |

#### Tool Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tool_code` | `string` | |
| `arguments_from` | `Record<string, string>` | 参数名 → state 路径 |
| `output_to` | `string` | 必须 `variables.*` |

#### Assign Node Data / Assign Op

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `assignments` | `AssignOp[]` | |
| `target`（Op） | `string` | `variables.*` 或 `metadata.*` |
| `expr`（Op） | `string` | 从三槽取值 |

#### Hitl Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `prompt_template` | `string` | |
| `form_schema` | `Record<string, unknown> \| null` | 待办表单 JSON Schema |
| `on_reject` | `"fail" \| "route"` | `route` 走 `hitl_decision` 分支 |

HITL **恢复 HTTP** 见「Workflow Execution」：会话属主或超管可列出/恢复 `pending`。节点仍可出现在图上。

#### Subgraph Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `flow_code` | `string` | 目标 Flow `code` |
| `version` | `number \| null` | 空则当前 published |
| `input_map` | `StateMapEntry[]` | |
| `output_map` | `StateMapEntry[]` | |
| `timeout_seconds` | `number \| null` | |

不展开子节点。画布下钻读目标 Flow 的 `definition.view`。

#### State Map Entry

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `from_path` | `string` | 如 `variables.foo`、`messages` |
| `to_path` | `string` | |

#### Custom Node Data

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `handler_key` | `string` | worker 注册表键 |
| `config` | `Record<string, unknown>` | 默认 `{}` |

#### Flow Edge

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | 与 branch `id` 不冲突 |
| `source` | `string` | 节点 id |
| `target` | `string` | 节点 id 或 `__end__` |
| `label` | `string \| null` | 仅展示 |

#### Flow Branch / Branch Router / Branch Case

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | |
| `source` | `string` | 单一源节点 |
| `router.kind` | `"state_path" \| "expr" \| "hitl_decision" \| "child_status"` | |
| `router.path` | `string \| null` | `state_path` |
| `router.expr` | `string \| null` | `expr` |
| `cases` | `{ key: string, target: string }[]` | `target` 可为 `__end__` |
| `default_target` | `string \| null` | |
| `max_visits` | `number \| null` | 回边上限 |

#### Flow View（仅表示层）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | `Record<string, NodeLayout>` | `id →` 坐标 |
| `edges` | `Record<string, EdgeLayout>` | |
| `branches` | `Record<string, EdgeLayout>` | |
| `groups` | `Record<string, unknown>[] \| null` | 无编译语义 |
| `computed_levels` | `Record<string, number> \| null` | BFS 缓存，保存前可重算 |

#### Node Layout / Edge Layout

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `x` / `y` | `number` | |
| `w` / `h` | `number \| null` | |
| `z` | `number \| null` | |
| `waypoints` | `number[][] \| null` | `[[x,y], ...]` |
| `color` | `string \| null` | |

空图约定（与 `empty_flow_definition` 一致）：节点 `start`/`end`，边 `e-start-end`，`view` 可空。

### 可运行对象

#### Flow Canvas Session

##### 类 `FlowCanvasSession`（约定）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `flowId` | `string \| null` | |
| `document` | `FlowDefinitionV1` | 正在编辑的图 |
| `dirty` | `boolean` | 相对上次保存 |
| `selection` | `{ kind: "node" \| "edge" \| "branch", id: string } \| null` | |

##### 运行方法（约定）

| 方法 | 说明 |
| --- | --- |
| `load(flowId)` | `GET /studio/flows/{id}` |
| `save()` | `PATCH` draft |
| `publish()` / `newDraft()` | 对应 POST |
| `setView(view)` | 只改 `view`，不改拓扑 |
| `setTopology(...)` | 改 nodes/edges/branches；发布前由服务端再校验 |

### 视图模型

#### Canvas Selection View

由 `FlowCanvasSession.selection` 派生属性面板：按 `NodeType` 展示对应 `data` 表单。子图下钻用 `PublishedFlowCodeOut` 选 `flow_code`。

---

## Models（LLM 目录）

`app_key=models`。可见可用：列表/详情；完全控制：创建/PATCH/停用。无行级绑定。密钥不出现在响应 `config`；以 `has_api_key` 表示。

`provider`：`openai` | `azure` | `local`。非法 `400 provider_invalid`；code 冲突 `409 llm_code_conflict`；`404 llm_not_found`。

### 传输对象

#### Llm Create Body

`POST /api/v1/models/llms`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `string` | 1–64 |
| `provider` | `string` | 1–32 |
| `model_name` | `string` | 1–128 |
| `config` | `Record<string, unknown>` | 可含 `api_key` / `apiKey` |
| `is_active` | `boolean` | 默认 `true` |

#### Llm Patch Body

`PATCH /api/v1/models/llms/{id}`。`config.api_key` 省略或空字符串表示**不覆盖**已有密钥。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `provider` | `string \| null` | |
| `model_name` | `string \| null` | |
| `config` | `Record<string, unknown> \| null` | |
| `is_active` | `boolean \| null` | |

#### Llm Out

列表与详情。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | |
| `code` | `string` | |
| `provider` | `string` | |
| `model_name` | `string` | |
| `is_active` | `boolean` | |
| `config` | `Record<string, unknown>` | **已去掉**密钥键 |
| `has_api_key` | `boolean` | 是否已配置密钥 |

查询：`offset` / `limit` / `is_active`（可选）。`POST .../deactivate`：`is_active=false`，响应仍为 `LlmOut`。

### 可运行对象

（无独立运行时。表单提交走 HttpClient。）

### 视图模型

#### Llm Form View

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `record` | `LlmOut \| null` | 编辑时 |
| `apiKeyInput` | `string` | 只写；提交后清空；**禁止**用 `record.config` 回填密钥 |
| `hasApiKey` | `boolean` | 来自 `has_api_key`，用于「已配置」提示 |

---

## Agent Config（Profile / Skill / Tool / MCP / Beat / 绑定）

`app_key=agent_config`。可见可用或完全控制。普通人列表/详情仅命中绑定且 actions 含 `read`/`use`/`write`/`admin` 的资源；未绑定不可见；越权详情 **`404` 不 `403`**。完全控制者与超管可见全部配置（含未绑定）。

创建配置时服务端登记 `sys_asset`（客户端不建模 Assets 表）。`PUT .../bindings` 仅完全控制或超管。Beat **无行级绑定**：可见可用即可列表/详情，完全控制才能创建/改/启停。

code 冲突 `409`。缺引用 `400`（`llm_not_found` / `skill_not_found` / `tool_not_found` / `mcp_server_not_found` / `flow_not_found` / `profile_not_found` / `mcp_server_required`）。非法 cron：`400 cron_invalid`。

不按 `owner_organization_id` 过滤。组织不沿父级继承。

### 传输对象

#### Profile Create / Patch / Out

路径：`/api/v1/agent-config/profiles`。

| 字段 | Create | Patch | Out | 说明 |
| --- | --- | --- | --- | --- |
| `id` | — | — | UUID 字符串 | |
| `code` | 必填 1–64 | — | 有 | |
| `name` | 必填 1–128 | 可选 | 有 | |
| `system_prompt` | 必填 | 可选 | 有 | |
| `default_llm_id` | 可选 | 可选 | 可空 | |
| `skill_ids` | 默认 `[]` | 可选 | 有 | UUID 字符串数组 |

绑定：`GET/PUT .../profiles/{id}/bindings`，体为 `BindingPutBody`，响应 `BindingItem[]`。

#### Skill Create / Patch / Out

路径：`/api/v1/agent-config/skills`。

| 字段 | Create | Patch | Out |
| --- | --- | --- | --- |
| `id` | — | — | 有 |
| `code` | 必填 | — | 有 |
| `name` | 必填 | 可选 | 有 |
| `description` | 可选 | 可选 | 可空 |
| `tool_ids` | 默认 `[]` | 可选 | 有 |
| `prompt_template` | 可选 | 可选 | 可空 |

#### Tool Create / Patch / Out

路径：`/api/v1/agent-config/tools`。`kind=mcp` 必须 `mcp_server_id`。

JSON 字段名 **`schema`**（参数 JSON Schema），不是 `parameter_schema`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | 仅 Out |
| `code` | `string` | 创建必填 |
| `name` | `string` | |
| `kind` | `"builtin" \| "http" \| "mcp"` | |
| `schema` | `Record<string, unknown>` | 参数定义 |
| `config` | `Record<string, unknown>` | HTTP URL 等；URL 仅来自配置 |
| `mcp_server_id` | `string (UUID) \| null` | |

#### Mcp Create / Patch / Out

路径：`/api/v1/agent-config/mcp-servers`。本轮不探测连通。`transport`：`stdio` | `sse`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | 仅 Out |
| `code` | `string` | |
| `name` | `string` | |
| `transport` | `"stdio" \| "sse"` | |
| `config` | `Record<string, unknown>` | 命令行、URL、env；**响应是否含密钥以现网为准**，UI 按敏感字段不回显处理 |
| `is_active` | `boolean` | |

#### Beat Create / Patch / Out

路径：`/api/v1/agent-config/beat-tasks`。`POST .../enable`、`.../disable`。

创建时 `flow_id` 与 `profile_id` **恰一**：皆空 `400 beat_target_required`；皆有 `400 beat_target_conflict`。PATCH **只改** `cron` / `input_payload`。

| 字段 | Create | Patch | Out | 说明 |
| --- | --- | --- | --- | --- |
| `id` | — | — | 有 | |
| `code` | 必填 | — | 有 | |
| `flow_id` | 可选 | — | 可空 | 工作流定时 |
| `profile_id` | 可选 | — | 可空 | 规划定时 |
| `cron` | 必填 | 可选 | 有 | |
| `input_payload` | 默认 `{}` | 可选 | 有 | |
| `is_enabled` | 默认 `true` | — | 有 | 启停走专用 POST |
| `last_triggered_at` | — | — | ISO 或 `null` | |

### 可运行对象

（无。绑定编辑为表单覆盖写入，不是增量 grant 协议。）

### 视图模型

#### Binding Editor View

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `resourceType` | `"application" \| "profile" \| "skill" \| "tool" \| "mcp_server"` | 应用走 `/auth/apps/.../bindings` |
| `resourceId` | `string` | 配置主键；应用则为 `app_key`（路径参数） |
| `rows` | `BindingItem[]` | GET 结果；PUT 时整表提交 |
| `canEdit` | `boolean` | `can_control` 或超管（由应用可见性推断） |

主体下拉所需的组织/用户目录 API **未开放**，编辑器可先手填 UUID，目录空章补齐后再换选择器。

#### Beat Target View

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | `"workflow" \| "planner"` | UI 互斥；提交时只带对应 id |

---

## Workflow Execution and Scheduling

会话发消息已返回 `run_id` 与 SSE 生命周期。HITL 待办与恢复已开放；**Run 列表、取消、子图 waiting 管理 HTTP 仍未开放**。

会话行**没有** `run_id` 外键；前端用 `SendMessageOut.run_id` 与 SSE `data.run_id` 关联本轮执行。

### 传输对象

#### HitlPendingOut

`GET /api/v1/conversations/workflow/hitl-pendings`、`GET .../hitl-pendings/{hitl_id}`。仅 `status=pending` 出现在列表。越权或不存在 `404 hitl_not_found`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string (UUID)` | 待办 id |
| `run_id` | `string (UUID)` | |
| `conversation_id` | `string (UUID) \| null` | 来自 Run |
| `node_id` | `string` | 中断节点 |
| `prompt` | `string` | |
| `form_schema` | `Record<string, unknown> \| null` | 写入 pending 的表单 schema |
| `status` | `string` | 列表恒为 `pending` |
| `expires_at` | `string \| null` | ISO 8601 |

查询：`run_id` 可选。普通人只看自己 Run 的待办；`is_superuser` 可看全部。

#### HitlResumeBody / HitlResumeOut

`POST .../hitl-pendings/{hitl_id}/resume`。非 pending：`400 hitl_not_resumable`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `decision` | `"approve" \| "reject"` | |
| `user_input` | `string \| null` | 可选 |
| `run_id`（出） | `string (UUID)` | |
| `resumed`（出） | `boolean` | `reject` 且 `on_reject=fail` 时为 false |

本轮另复用：`SendMessageOut.run_id`；SSE：`run_submitted` / `run_interrupted` / `run_completed` / `run_failed`。

下列仍待补：`RunOut`、`CancelRunBody`、子图 pending 列表。

服务端 Run 状态枚举：`pending` / `running` / `interrupted` / `waiting_child` / `completed` / `failed` / `cancelled`。

### 可运行对象

（待补：`RunMonitorClient`。HITL 用待办 API；一轮执行仍用 `ConversationSseClient`。）

### 视图模型

#### Active Run Chip

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `runId` | `string \| null` | 来自最近一次 `SendMessageOut` 或 SSE |
| `phase` | `SseClientState` | 与 SSE 客户端相同 |

---

## Knowledge, Files and Retrieval Index

本轮应用层**无**集合/文档/检索/分片上传 HTTP。服务端见 `data_schema_server.md` 对应章。原文在 MinIO；chunk 对齐向量与全文。

### 传输对象

（待补：`CollectionOut`、`DocOut`、`SearchQuery` / `SearchHit`、`UploadSessionOut`、`UploadPartDescriptor`。）

### 可运行对象

（待补：入库进度轮询、分片上传会话。）

### 视图模型

（待补：检索结果列表、入库进度条。）

---

## Graph Knowledge

本轮应用层**无**图查询 HTTP。领域图不承载 LangGraph 工作流。

### 传输对象

（待补：`GraphTraversalQuery`、`GraphQueryResult`。）

### 可运行对象

（待补。）

### 视图模型

（待补：多跳可视化节点/边。）

---

## Security and Rate Limit

护栏在图节点内执行；本轮**无限流 HTTP**、无规则管理 API。流式 `speaking` 不经护栏。

### 传输对象

（待补：`GuardrailRuleOut`、`PolicyViolationOut`。若未来 `429`，再定限流响应头/体。）

### 可运行对象

（无。不要在浏览器内跑护栏模型。）

### 视图模型

（待补：违规提示条。被 `block` 时以会话消息 `failed` 或错误体为准。）

---

## Audit and Usage

本轮应用层**无**审计查询 / 用量仪表 HTTP。

### 传输对象

（待补：`ActivityOut`、`UsageMeterReading`。）

### 可运行对象

（待补。）

### 视图模型

（待补：用量进度相对 `limit`。）

---

## Observability and Trace

本轮应用层**无** Trace/Span/LLM 调用查询 HTTP。Prompt 仅服务端脱敏入库。

### 传输对象

（待补：`TraceOut`、`SpanOut`、`LlmCallOut`。）

### 可运行对象

（待补。）

### 视图模型

（待补：flame 时间线。禁止把未脱敏 prompt 拉到浏览器。）

---

## Notification

本轮应用层**无** Webhook 端点管理 HTTP。

### 传输对象

（待补：`WebhookEndpointOut`（响应不得回显 `secret` 明文）、`DeliveryLogOut`。）

### 可运行对象

（待补。）

### 视图模型

（待补。）

---

## 不进入客户端对照表

无论对应域是否已有 HTTP，下列内容禁止出现在传输对象、可运行对象持久化字段与视图模型中。

| 类别 | 示例 |
| --- | --- |
| 密钥与摘要 | `password_hash`、LLM `api_key` 响应、Webhook `secret` 明文、LDAP `bind_password` |
| Redis | `auth:jwt:blacklist:*`、`conv:stream:*`、`wf:run:active:*`、限流桶 |
| 调度内部 | `CeleryTaskEnvelope`、worker_id、checkpointer 字节、`langgraph_thread_id` 除非未来调试 API 明确下发 |
| 注册表 | 前端私自维护 Application/Service 绑定表 |
| ORM 软删除列等 | `deleted_at`（现网 Out 未下发则不建模） |

---

## 与其它文档、实现的关系

| 文档 / 代码 | 关系 |
| --- | --- |
| [data_schema_server.md](./data_schema_server.md) | 服务端三类形态与表；客户端不复制 ORM |
| [api_reference_server.md](./api_reference_server.md) | 路径、错误码、两档 RBAC |
| `api/apps/*/schemas.py` | 现网 JSON 字段的权威实现 |
| `service/runtime/definition_v1.py` | Flow v1 与 Studio `definition` 共用 |
| `docs/plan/unreached/2026-08-20-自主规划与模型管理前端-表示层-修改.md` | 表示层实现仍 unreached；落地时按本文生成 TS 类型 |
