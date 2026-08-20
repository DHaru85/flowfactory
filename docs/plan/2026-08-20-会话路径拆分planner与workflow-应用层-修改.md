# 2026-08-20 会话路径拆分 planner 与 workflow - 应用层 - 修改

总纲：`2026-08-20-自主规划智能体与模型管理-应用层服务层-修改.md`（第 2 轮）。
来源：`docs/plan/unreached/2026-08-20-会话路径拆分planner与workflow-应用层-修改.md`。

**状态：已锁定。** 2026-08-20 用户确认后开工。

## 用户需求理解

继续推进自主规划智能体**会话应用**：规划会话与工作流直连会话共用 `conv_*` 仓储与 SSE，HTTP 按场景分路径（总纲 Q1、Q6）：

- `/api/v1/conversations/planner*`
- `/api/v1/conversations/workflow*`

`profile_id` 写入会话 `metadata`；列表简要不带该字段，进详情再加载。不另建历史表。不建设规划主循环（第 3 轮）、不接 RBAC 审核、不做前端。

### 澄清过程

见总纲「澄清过程」Q1、Q6、Q8。本轮对应第 2 轮「会话路径拆分」。

开工前复核（原 unreached 待办，本轮取默认）：

- **保留**现网 `/api/v1/conversations` 与 `/api/v1/conversations/{id}` 等路径，作为 **workflow 兼容别名**（`app_key` 为 `workflow` 或历史值 `conversation`），避免已有客户端与集成测试断裂。
- 新客户端应使用 `/workflow*` / `/planner*`。

## 需求中的待澄清事项

无待澄清事项（本轮范围；别名策略取上述默认，确认时可推翻）。

## 施工方案

> 用户确认后视为锁定。第 3 轮规划循环仍在 `docs/plan/unreached/`。

### 1. 应用边界

仍为一个 `conversation` Application（`app_key=conversation` 表示应用注册，与会话行上的 `app_key` 字段不同）。

会话行 `app_key`：

| 场景 | 会话 `app_key` | 路径前缀 |
| --- | --- | --- |
| 工作流直连（新） | `workflow` | `/api/v1/conversations/workflow` |
| 工作流直连（兼容） | `conversation` 或 `workflow` | `/api/v1/conversations`（无中间段） |
| 规划智能体 | `planner` | `/api/v1/conversations/planner` |

不新增独立 `planner` FastAPI 应用。不调用 `PermissionService`。

静态前缀路由（`/planner`、`/workflow`、`/messages`）必须注册在 `/{conversation_id}` 之前，避免把 `planner` / `workflow` 当成 UUID。

### 2. 路由一览

**规划（`/planner`）**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/conversations/planner` | 仅当前用户、`app_key=planner`；列表项无 `metadata` / `profile_id` |
| POST | `/api/v1/conversations/planner` | 必填 `profile_id`；写入 `metadata.profile_id`；`app_key=planner`；`flow_id` 为空 |
| GET | `/api/v1/conversations/planner/{id}` | 详情含 `metadata`（可读 `profile_id`）；非 planner 会话 404 |
| GET | `/api/v1/conversations/planner/{id}/messages` | 同现网消息列表 |
| POST | `/api/v1/conversations/planner/messages` | 见第 4 节 |
| GET | `/api/v1/conversations/planner/{id}/events` | SSE，协议不变 |

**工作流（`/workflow`）**

与现网语义对齐，列表/详情仅 `app_key in (workflow, conversation)`（新创建写 `workflow`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/v1/conversations/workflow` | 创建可带 `flow_id`；`app_key=workflow` |
| GET | `/api/v1/conversations/workflow/{id}` | 非本场景会话 404 |
| GET | `.../messages`、`.../events` | 同现网 |
| POST | `/api/v1/conversations/workflow/messages` | 仍要求 `flow_id`（body 或会话上已有），入队 `WorkflowRuntimeService.start` |

**兼容别名（现网路径）**

`GET/POST /api/v1/conversations`、`GET .../{id}`、`GET .../{id}/messages`、`POST .../messages`、`GET .../{id}/events` 行为与 `/workflow*` 相同（列表过滤同上）。现有集成测试可继续打旧路径。

跨场景用错前缀：按「会话不存在」返回 `404 conversation_not_found`（避免探查）。越权仍 `403 conversation_forbidden`。无 token `401`。

### 3. DTO 与仓储

- 列表：`ConversationOut` 不含 `metadata`（因此不含 `profile_id`）。
- 详情：`ConversationDetailOut` 在列表字段上增加 `metadata: dict`。
- `POST /planner` 与 planner 发消息：`profile_id: UUID` 必填（创建）或可从会话 metadata 继承（续聊）。Profile 不存在：`400 profile_not_found`。不把 `profile_id` 写成 `conv_conversation.flow_id`。
- `ConversationRepository.list_by_user` 增加可选 `app_keys: Sequence[str] | None`，SQL 过滤；不改表结构、无 Alembic。

### 4. 发消息（本轮规划循环未落地）

- **workflow / 兼容路径**：与现网一致：写 user + assistant（streaming）→ `runtime.start` → `run_submitted`。缺 `flow_id`：`400 flow_id_required`。
- **planner**：校验归属与 `profile_id`（body 优先，否则 `metadata.profile_id`）；校验 Profile 存在。第 3 轮未开工，**不入队、不写 assistant streaming 占位**（避免无 run 的悬挂消息）。返回 **`501 planner_runtime_not_ready`**，不调用 `WorkflowRuntimeService.start`。用户确认第 3 轮完成后再改为入队规划 Run 并返回 `run_id`。
- 可选：planner 创建会话与列消息本轮可用，便于前端先挂入口。

### 5. 明确不做

- `SkillRuntime` / `PlannerRuntime` / Celery `kind=planner`
- 规划 Beat、`flow_id` 可空
- `PermissionService` 过滤
- 表示层
- 新会话表或拆 `conversation` Application

### 6. 文档与测试

- 更新 `api_reference_server.md` 第 3 节：两套前缀、兼容别名、planner 详情 metadata、planner 发消息 501。
- 单测/集成：401；workflow 发消息 Fake runtime 仍通；planner 列表不含 `profile_id`、详情含；planner 打 workflow id 404；越权 403；planner 发消息 501 且不调用 runtime；`/planner` 不被当成 UUID。
- ruff 无 error；现网 `test_send_message_and_sse` 旧路径回归。

### 7. 施工状态（确认开工后）

标记施工中：`应用层 / api`。仓储方法签名变更若落在 `service/persistence`，同时标记 `数据层 / service/persistence`。

不改 `service/runtime`、`celery_app`、映射层。完成后改回空闲，删除或清空对应 unreached 文件，写第 2 轮简报。不改历史 plan。

## 方案待澄清事项

无待澄清事项（确认即锁定）。若否定「旧路径作 workflow 别名」或「planner 发消息 501」，确认回复中指出即可改方案后再开工。

## 验收标准（锁定后生效）

1. `/planner*` 与 `/workflow*` 均可对己方会话做列表/创建/详情/消息列表/SSE 订阅；数据在同一 `conv_*`。
2. planner 详情可读 `metadata.profile_id`；对应列表项不含该字段。
3. 跨前缀访问他场景会话 404；越权 403；无 token 401。
4. planner 发消息 501 `planner_runtime_not_ready`，不启动 Flow。
5. 旧 `/api/v1/conversations*` 仍可走工作流 Fake 入队（回归）。
6. ruff 无 error；新增与回归测试通过；`api_reference_server.md` 覆盖本轮路径。
