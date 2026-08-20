# FlowFactory 后端数据结构设计说明

本文档按**功能领域**（二级标题）分区，整理记录工程的后端服务运行全生命周期所有的数据结构定义

## 分类说明

| 分类 | 含义 | 典型落点 |
| --- | --- | --- |
| **数据** | 经 ORM 映射管理、写入持久化存储的事实记录；含 Postgres 主库与 Redis 等需保留状态的缓存记录 | SQLAlchemy Model、Redis 结构化 key |
| **可运行对象** | 可被实例化、具备运行方法，并参与调度或业务流程的对象；彼此及与**数据**之间**不做表字段级外键关联**，由代码持有引用 | Python 类实例、注册表中的 Application / Service |
| **序列化对象** | 仅在**可运行对象**的方法调用链中，对入参、出参及中间结果做格式化与校验的对象；不单独承担调度职责 | Pydantic Schema、SSE 帧 DTO |

**补充约定**

- **数据**与**可运行对象**可一一对应两份形态：例如 Run 运行时是可运行对象，其「结果防丢 / HITL·Beat 中断现场」另以**数据**形态持久化，加载时再 hydrate 为内存实例。
- Checkpoint **底层记录**由 LangGraph Postgres checkpointer 写入，不在此重复建模；**Checkpoint Instance** 仅作为从持久化读出后的**可运行对象**内存形态。
- Application / Service 仅为代码引用与注册关系，**数据**域中不落绑定表；权限若需挂应用/服务，**数据**里 Assets 只存 `app_key` / `service_key` 等稳定标识。

---

## Permission Manage and LDAP Adapter

权限与身份。`Assets` 表可授权对象；`Quota` 表额度上限；消耗记账见 Audit。本域不含 Application / Service 绑定表，Assets 通过 `asset_type` + `asset_key` 引用代码侧稳定标识。

### 数据

#### User

##### ORM 表 `sys_user`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 用户主键 |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL | 登录名 |
| `email` | VARCHAR(255) | UNIQUE, NULL | 邮箱 |
| `password_hash` | VARCHAR(255) | NULL | 本地密码摘要；纯 LDAP 用户可为空 |
| `display_name` | VARCHAR(128) | NOT NULL | 展示名 |
| `organization_id` | UUID | FK → `sys_organization.id`, NOT NULL | 所属组织 |
| `department_id` | UUID | FK → `sys_department.id`, NULL | 所属部门 |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT `active` | `active` / `disabled` / `locked` |
| `is_superuser` | BOOLEAN | NOT NULL, DEFAULT false | 超管绕过 RBAC |
| `ldap_dn` | VARCHAR(512) | NULL | LDAP 专有名称；本地用户为空 |
| `last_login_at` | TIMESTAMPTZ | NULL | 最近登录时间 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | NULL | 软删除 |

索引：`idx_sys_user_org (organization_id)`、`idx_sys_user_dept (department_id)`、`idx_sys_user_ldap_dn (ldap_dn)` WHERE `ldap_dn IS NOT NULL`。

##### ORM 关联表 `sys_user_role`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `user_id` | UUID | PK, FK → `sys_user.id` | 用户 |
| `role_id` | UUID | PK, FK → `sys_role.id` | 角色 |
| `granted_at` | TIMESTAMPTZ | NOT NULL | 授予时间 |
| `granted_by` | UUID | FK → `sys_user.id`, NULL | 授予人 |

#### Organization

##### ORM 表 `sys_organization`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 组织主键 |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | 组织编码 |
| `name` | VARCHAR(128) | NOT NULL | 组织名称 |
| `parent_id` | UUID | FK → `sys_organization.id`, NULL | 上级组织；根节点为空 |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT `active` | `active` / `disabled` |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

#### Department

##### ORM 表 `sys_department`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 部门主键 |
| `organization_id` | UUID | FK → `sys_organization.id`, NOT NULL | 所属组织 |
| `code` | VARCHAR(64) | NOT NULL | 部门编码；组织内唯一 |
| `name` | VARCHAR(128) | NOT NULL | 部门名称 |
| `parent_id` | UUID | FK → `sys_department.id`, NULL | 上级部门 |
| `path` | VARCHAR(512) | NULL | 物化路径，如 `/root/eng/backend` |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

唯一约束：`UNIQUE (organization_id, code)`。

#### Role

##### ORM 表 `sys_role`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 角色主键 |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | 角色编码，如 `knowledge_admin` |
| `name` | VARCHAR(128) | NOT NULL | 角色名称 |
| `description` | TEXT | NULL | 说明 |
| `scope` | VARCHAR(16) | NOT NULL | `global` / `organization` |
| `organization_id` | UUID | FK → `sys_organization.id`, NULL | `scope=organization` 时必填 |
| `is_system` | BOOLEAN | NOT NULL, DEFAULT false | 系统内置角色不可删 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

##### ORM 关联表 `sys_role_asset_grant`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `role_id` | UUID | PK, FK → `sys_role.id` | 角色 |
| `asset_id` | UUID | PK, FK → `sys_asset.id` | 可授权资源 |
| `actions` | JSONB | NOT NULL | 动作集合，如 `["read","write","admin"]` |
| `granted_at` | TIMESTAMPTZ | NOT NULL | 授予时间 |

#### Assets

##### ORM 表 `sys_asset`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 资源主键 |
| `asset_type` | VARCHAR(32) | NOT NULL | `application` / `service` / `knowledge_collection` / `flow` / `file` / `profile` / `skill` / `tool` / `mcp_server` 等 |
| `asset_key` | VARCHAR(128) | NOT NULL | 稳定标识，如 `app_key`、`service_key` |
| `name` | VARCHAR(128) | NOT NULL | 展示名 |
| `owner_organization_id` | UUID | FK → `sys_organization.id`, NULL | 归属组织 |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | 扩展属性 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

唯一约束：`UNIQUE (asset_type, asset_key)`。

##### Hot Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `auth:asset:{asset_type}:{asset_key}` | HASH | 300s | 资源元数据热读；字段 `id,name,owner_organization_id` |
| `auth:role_grants:{role_id}` | STRING (JSON) | 300s | 角色对 Assets 的 `actions` 列表 |

#### Quota

##### ORM 表 `sys_quota`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 配额主键 |
| `subject_type` | VARCHAR(16) | NOT NULL | `user` / `organization` / `role` |
| `subject_id` | UUID | NOT NULL | 主体 id |
| `quota_type` | VARCHAR(32) | NOT NULL | `llm_token` / `api_call` / `storage_bytes` 等 |
| `limit_value` | BIGINT | NOT NULL | 上限值 |
| `period` | VARCHAR(16) | NOT NULL | `daily` / `monthly` / `none` |
| `effective_from` | TIMESTAMPTZ | NULL | 生效起始 |
| `effective_to` | TIMESTAMPTZ | NULL | 生效结束 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

唯一约束：`UNIQUE (subject_type, subject_id, quota_type, period)`。

##### Hot Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `auth:quota:{subject_type}:{subject_id}:{quota_type}:{period}` | STRING | 与 period 对齐 | 当前周期已用量计数；Audit 域异步回写校准 |

#### Refresh Token

##### ORM 表 `sys_refresh_token`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 记录主键 |
| `user_id` | UUID | FK → `sys_user.id`, NOT NULL | 所属用户 |
| `token_hash` | VARCHAR(64) | UNIQUE, NOT NULL | refresh token 摘要（SHA-256 hex） |
| `family_id` | UUID | NOT NULL | 轮换族 id；重用旧 token 时吊销整族 |
| `jti` | UUID | UNIQUE, NOT NULL | 与 access token 族关联的标识 |
| `expires_at` | TIMESTAMPTZ | NOT NULL | 过期时间 |
| `revoked_at` | TIMESTAMPTZ | NULL | 吊销时间 |
| `user_agent` | VARCHAR(512) | NULL | 签发时 UA |
| `client_ip` | INET | NULL | 签发时 IP |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |

索引：`idx_refresh_token_user (user_id)`、`idx_refresh_token_family (family_id)`。

#### Ldap Sync Job

##### ORM 表 `sys_ldap_sync_job`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 作业主键 |
| `trigger` | VARCHAR(16) | NOT NULL | `manual` / `scheduled` |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `running` / `success` / `failed` |
| `started_at` | TIMESTAMPTZ | NULL | 开始时间 |
| `finished_at` | TIMESTAMPTZ | NULL | 结束时间 |
| `stats` | JSONB | NOT NULL, DEFAULT `{}` | 如 `{"created":0,"updated":1,"disabled":0}` |
| `error_message` | TEXT | NULL | 失败原因 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |

#### External Identity Mapping

##### ORM 表 `sys_external_identity`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 映射主键 |
| `provider` | VARCHAR(32) | NOT NULL | 固定 `ldap` |
| `external_id` | VARCHAR(512) | NOT NULL | LDAP entryUUID 或稳定 id |
| `ldap_dn` | VARCHAR(512) | NOT NULL | 目录 DN |
| `user_id` | UUID | FK → `sys_user.id`, NOT NULL | 本地用户 |
| `attrs_snapshot` | JSONB | NOT NULL, DEFAULT `{}` | 最近同步的 LDAP 属性快照 |
| `last_synced_at` | TIMESTAMPTZ | NOT NULL | 最近同步时间 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |

唯一约束：`UNIQUE (provider, external_id)`、`UNIQUE (provider, ldap_dn)`。

#### JWT status（Redis，黑名单 / 会话态）

##### Redis Key 定义

| Key 模式 | 类型 | TTL | Value | 说明 |
| --- | --- | --- | --- | --- |
| `auth:jwt:blacklist:{jti}` | STRING | access token 剩余有效期 | `"1"` | 登出、踢人、改密后作废 access token |
| `auth:jwt:revoke_before:{user_id}` | STRING | 可选长期或随改密更新 | Unix 时间戳 | 该时刻之前签发的 token 一律无效 |
| `auth:session:index:{user_id}` | SET | 与 refresh 最长 TTL 对齐 | refresh `jti` 集合 | 一键踢掉用户全部会话 |

### 可运行对象

#### Ldap Adapter（目录同步与身份映射执行体）

##### 类 `LdapAdapter`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `config` | `LdapConnectionConfig`（序列化对象） | 连接与搜索基准 DN 等配置 |
| `_client` | LDAP 客户端实例 | 进程内连接，不参与 ORM |

##### 运行方法

| 方法 | 入参（序列化对象） | 出参（序列化对象） | 说明 |
| --- | --- | --- | --- |
| `connect()` | — | — | 建立目录连接 |
| `close()` | — | — | 释放连接 |
| `fetch_entries()` | `LdapSearchFilter` | `list[LdapEntrySnapshot]` | 按过滤器拉取条目 |
| `sync_users()` | `LdapSyncPayload` | `LdapSyncResult` | 全量/增量同步用户；写 `sys_user`、`sys_external_identity` |
| `sync_departments()` | `LdapSyncPayload` | `LdapSyncResult` | 同步组织/部门树 |
| `map_identity()` | `LdapEntrySnapshot` | `ExternalIdentityMapping`（数据 hydrate） | 单条目映射为本地用户 |

##### 调度约定

- 由 Celery Beat 或管理台手动触发；每次运行创建一条 `sys_ldap_sync_job` 记录。
- 与 **User / Organization / Department** 数据表通过代码写入关联，**不**在 Adapter 实例上挂 ORM 外键字段。

#### AuthService（登录、签发、校验、吊销）

##### 类 `AuthService`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `user_repo` | User 仓储 | 读 `sys_user` |
| `refresh_repo` | RefreshToken 仓储 | 读写的 `sys_refresh_token` |
| `jwt_codec` | JWT 编解码器 | 验签、解析 `TokenClaims` |
| `redis` | Redis 客户端 | 读写 JWT status key |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `login()` | `LoginCredentials` | `TokenPairResponse` | 校验凭据，签发 access + refresh |
| `refresh()` | `RefreshTokenRequest` | `TokenPairResponse` | 轮换 refresh；重用检测吊销 `family_id` |
| `logout()` | `LogoutRequest` | — | access `jti` 入黑名单；refresh 标记 `revoked_at` |
| `revoke_all_sessions()` | `user_id: UUID` | — | 更新 `revoke_before` 并清空 session index |
| `verify_access_token()` | `raw_token: str` | `TokenClaims` | 验签 + 黑名单 + `revoke_before` |

#### PermissionService（RBAC 校验）

##### 类 `PermissionService`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `grant_cache` | 可选 Redis | 读 `auth:role_grants:*`、`auth:asset:*` |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `check()` | `PermissionCheckRequest` | `PermissionCheckResult` | 超管直通；否则合并用户角色与 Asset grant |
| `list_accessible_assets()` | `user_id`, `asset_type`, `action` | `list[AssetRef]` | 列出某动作下可访问资源 |

### 序列化对象

#### Login Credentials

##### Pydantic `LoginCredentials`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `username` | str | min_length=1, max_length=64 | 登录名 |
| `password` | str | min_length=1 | 明文密码，仅传输层 TLS 保护，不入库 |

#### Token Claims

##### Pydantic `TokenClaims`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `sub` | UUID | — | 用户 id |
| `jti` | UUID | — | token 唯一 id |
| `iat` | int | — | 签发时间 |
| `exp` | int | — | 过期时间 |
| `org_id` | UUID | — | 当前组织 |
| `roles` | list[str] | — | 角色 code 列表 |
| `token_type` | Literal[`access`] | — | 固定 `access` |

#### Token Pair Response

##### Pydantic `TokenPairResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `access_token` | str | 短 JWT |
| `refresh_token` | str | opaque 或 JWT refresh |
| `expires_in` | int | access 秒数 |
| `token_type` | Literal[`Bearer`] | 固定 `Bearer` |

#### Refresh Token Request

##### Pydantic `RefreshTokenRequest`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `refresh_token` | str | 客户端持有的 refresh token |

#### Logout Request

##### Pydantic `LogoutRequest`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `access_jti` | UUID | 当前 access token 的 jti |
| `refresh_token` | str | NULL 则仅吊销 access |

#### Permission Check Request / Result

##### Pydantic `PermissionCheckRequest`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | UUID | 待校验用户 |
| `asset_type` | str | 与 `sys_asset.asset_type` 一致 |
| `asset_key` | str | 与 `sys_asset.asset_key` 一致 |
| `action` | str | `read` / `write` / `admin` 等 |

##### Pydantic `PermissionCheckResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `allowed` | bool | 是否允许 |
| `reason` | str | NULL | 拒绝原因，如 `missing_grant` |

#### Ldap Sync Payload

##### Pydantic `LdapSyncPayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | UUID | 对应 `sys_ldap_sync_job.id` |
| `mode` | Literal[`full`, `incremental`] | 同步模式 |
| `since` | datetime | NULL | 增量水位；`incremental` 时使用 |
| `user_filter` | str | NULL | LDAP 过滤器 override |
| `dry_run` | bool | 默认 false | 只统计不写库 |

##### Pydantic `LdapSyncResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `created` | int | 新建用户数 |
| `updated` | int | 更新用户数 |
| `disabled` | int | 禁用用户数 |
| `errors` | list[str] | 非致命错误摘要 |

##### Pydantic `LdapEntrySnapshot`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dn` | str | LDAP DN |
| `external_id` | str | entryUUID |
| `username` | str | sAMAccountName / uid |
| `email` | str | NULL |
| `display_name` | str | |
| `department_dn` | str | NULL |
| `attrs` | dict[str, Any] | 原始属性 |

##### Pydantic `LdapSearchFilter`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `base_dn` | str | 搜索基准 |
| `filter_expr` | str | LDAP 过滤器 |
| `attributes` | list[str] | 拉取属性列表 |

##### Pydantic `LdapConnectionConfig`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `host` | str | 目录地址 |
| `port` | int | 默认 389 / 636 |
| `use_tls` | bool | |
| `bind_dn` | str | 服务账号 DN |
| `bind_password` | SecretStr | 不写日志 |
| `user_search_base` | str | 用户搜索基准 |
| `group_search_base` | str | NULL | 组/部门搜索基准 |


## Application and Service Registry

一类交互场景对应一个 Application；Service 可被多个 Application 组合引用。**不落绑定表**，组合关系在 Python 注册代码中声明；Permission 域 `sys_asset` 通过 `asset_type` + `asset_key` 做授权。

### 数据

（无独立 ORM 表；元数据可选登记到 Permission 域 `sys_asset`，`asset_type` 为 `application` / `service`）

### 可运行对象

#### Application

##### 类 `Application`（抽象基类或 Protocol）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `app_key` | `ClassVar[str]` | 稳定标识，与 `sys_asset.asset_key` 对齐 |
| `name` | `ClassVar[str]` | 展示名 |
| `services` | `list[type[Service]]` | 代码声明引用的 Service 类列表 |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `on_startup()` | `ApplicationContext` | — | 进程启动钩子 |
| `build_router()` | — | `APIRouter` | 挂载本应用 REST 路由 |
| `resolve_services()` | — | `list[Service]` | 实例化所引用的 Service |

##### 注册约定

- 启动时扫描 `api/apps/` 包，将 `Application` 子类注册进 `ApplicationRegistry`（进程内单例 dict，`app_key → Application` 实例）。
- **Application 之间、Application 与 Service 之间无表字段外键**，仅 Python 引用。

#### Service

##### 类 `Service`（抽象基类或 Protocol）

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `service_key` | `ClassVar[str]` | 稳定标识 |
| `name` | `ClassVar[str]` | 展示名 |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `on_startup()` | `ServiceInvokeContext` | — | 初始化连接池、客户端等 |
| `health_check()` | — | `bool` | 就绪探针 |

##### 注册约定

- `ServiceRegistry`：`service_key → Service` 单例；由 Application 在运行时按类引用获取，**不持久化绑定关系**。

#### ApplicationRegistry / ServiceRegistry

##### 类 `ApplicationRegistry`

| 方法 | 说明 |
| --- | --- |
| `register(app: Application)` | 注册应用；`app_key` 冲突则启动失败 |
| `get(app_key: str) -> Application` | 按 key 获取 |
| `list_keys() -> list[str]` | 列举已注册应用 |

##### 类 `ServiceRegistry`

| 方法 | 说明 |
| --- | --- |
| `register(service: Service)` | 注册服务 |
| `get(service_key: str) -> Service` | 按 key 获取 |

### 序列化对象

#### Application Context

##### Pydantic `ApplicationContext`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `app_key` | str | 当前应用标识 |
| `settings` | dict[str, Any] | 应用级配置快照 |
| `user_id` | UUID | NULL | 触发 startup 的操作者，可选 |

#### Service Invoke Context

##### Pydantic `ServiceInvokeContext`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `service_key` | str | 服务标识 |
| `caller_app_key` | str | 调用方 Application |
| `request_id` | str | 链路 id |
| `user_id` | UUID | NULL | 当前用户 |

---

## Conversation and Session SSE Protocol

会话事实入库；下行 SSE 为推送协议，事件帧对应 Message 的 `content_blocks`，不按 event type 各建一张表。一次用户发送触发 Agent Run，Conversation 与 Run 在代码中关联，**不做 Run 外键字段**（见 Workflow 域）。

### 数据

#### Conversation

##### ORM 表 `conv_conversation`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 会话主键 |
| `user_id` | UUID | FK → `sys_user.id`, NOT NULL | 所属用户 |
| `title` | VARCHAR(256) | NULL | 标题；可由首条消息生成 |
| `app_key` | VARCHAR(128) | NOT NULL | 发起会话的应用标识 |
| `flow_id` | UUID | NULL | 关联 Flow 配置 id；逻辑引用，非强制 FK |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT `active` | `active` / `archived` / `deleted` |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | 扩展字段；规划会话存 `profile_id`（UUID 字符串） |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

索引：`idx_conv_user_updated (user_id, updated_at DESC)`。

#### Message

##### ORM 表 `conv_message`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 消息主键 |
| `conversation_id` | UUID | FK → `conv_conversation.id`, NOT NULL | 所属会话 |
| `role` | VARCHAR(16) | NOT NULL | `user` / `assistant` / `system` / `tool` |
| `content_blocks` | JSONB | NOT NULL, DEFAULT `[]` | 结构化内容块，见 `MessageContentBlock` |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT `completed` | `streaming` / `completed` / `failed` / `cancelled` |
| `token_usage` | JSONB | NULL | 如 `{"prompt":100,"completion":50}` |
| `created_at` | TIMESTAMPTZ | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | 更新时间 |

索引：`idx_conv_message_conversation (conversation_id, created_at)`。

##### Cache（活跃流式状态）

| Key 模式 | 类型 | TTL | Value | 说明 |
| --- | --- | --- | --- | --- |
| `conv:stream:{message_id}` | STRING | 600s | 当前已推送文本片段 | 断线重连增量对齐 |
| `conv:sse:subscribers:{conversation_id}` | SET | 随 Session 生命周期 | connection id | 当前 SSE 订阅者 |

### 可运行对象

#### Session（会话生命周期与 SSE 推送调度）

##### 类 `Session`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | UUID | 绑定的会话 |
| `user_id` | UUID | 所属用户 |
| `_subscribers` | `asyncio.Queue[SseEvent]` 映射 | 进程内 SSE 推送队列 |
| `_run_handle` | `Run` | NULL | 当前关联的运行时可运行对象引用 |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `open()` | — | — | 注册订阅、加载最近 Message |
| `close()` | — | — | 清理 Redis 订阅 key |
| `send_user_message()` | `SendMessageRequest` | `SendMessageResponse` | 持久化 user Message，提交 Run |
| `push_event()` | `SseEvent` | — | 向所有订阅者广播 SSE 帧 |
| `attach_run()` | `Run` | — | 绑定当前 Agent 运行实例 |
| `finalize_assistant_message()` | `message_id`, `content_blocks` | — | 流结束写库 |

##### 调度约定

- 每个 SSE 连接对应一个 `Session` 实例；FastAPI `StreamingResponse` 消费 `push_event` 输出。
- `Run` 通过 `attach_run` 引用，**不在 `conv_conversation` 上存 run_id 字段**。

### 序列化对象

#### SSE Event（推送帧基类）

##### Pydantic `SseEvent`（基类）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | str | SSE `event:` 行 |
| `data` | dict[str, Any] | JSON 载荷 |
| `id` | str | NULL | SSE `id:`，用于 Last-Event-ID |

##### reasoning

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | Literal[`reasoning`] | |
| `data.delta` | str | 推理文本增量 |
| `data.message_id` | UUID | 关联 assistant Message |

##### tool_calling

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | Literal[`tool_calling`] | |
| `data.tool_call_id` | str | 工具调用 id |
| `data.tool_name` | str | |
| `data.arguments` | dict | 参数快照 |
| `data.status` | str | `started` / `completed` / `failed` |
| `data.result` | Any | NULL | 完成时的结果摘要 |

##### speaking

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | Literal[`speaking`] | |
| `data.delta` | str | 面向用户的回复 token 增量 |
| `data.message_id` | UUID | |

##### subagent_running

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | Literal[`subagent_running`] | |
| `data.subagent_key` | str | 子 Agent 标识 |
| `data.status` | str | `started` / `completed` |
| `data.summary` | str | NULL | 完成摘要 |

##### step_running

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | Literal[`step_running`] | |
| `data.node_id` | str | LangGraph 节点 id |
| `data.step_name` | str | 展示名 |
| `data.status` | str | `started` / `completed` / `failed` |

#### Message Content Block

##### Pydantic `MessageContentBlock`（discriminated union）

| 变体 | 字段 | 说明 |
| --- | --- | --- |
| `type=text` | `text: str` | 纯文本 |
| `type=reasoning` | `text: str` | 推理块 |
| `type=tool_call` | `tool_call_id, name, arguments, result?` | 工具调用块 |
| `type=artifact` | `mime_type, url, metadata` | 结构化产物引用 |

#### Send Message Request / Response

##### Pydantic `SendMessageRequest`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | UUID | NULL | 空则新建 Conversation |
| `app_key` | str | 应用标识 |
| `flow_id` | UUID | NULL | 指定 Flow |
| `content` | str | 用户输入文本 |
| `metadata` | dict | NULL | 客户端扩展 |

##### Pydantic `SendMessageResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` | UUID | |
| `user_message_id` | UUID | 已持久化的 user Message |
| `assistant_message_id` | UUID | 预创建的 streaming assistant Message |
| `run_id` | UUID | 已提交的 Run 标识（内存 id，见 Workflow 域） |

---

## Agent Configuration and Workflow Definitions

配置态：Profile、模型、工具、Flow 图定义等。编译后的 **Flow Runtime** 为可运行对象；运行现场见 Workflow 域。

### 数据

#### Profile

##### ORM 表 `agent_profile`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | 如 `default_assistant` |
| `name` | VARCHAR(128) | NOT NULL | |
| `system_prompt` | TEXT | NOT NULL | |
| `default_llm_id` | UUID | FK → `agent_llm.id`, NULL | |
| `skill_ids` | JSONB | NOT NULL, DEFAULT `[]` | Skill id 列表 |
| `owner_organization_id` | UUID | NULL | 多租户隔离 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Large Language Model

##### ORM 表 `agent_llm`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `provider` | VARCHAR(32) | NOT NULL | `openai` / `azure` / `local` 等 |
| `model_name` | VARCHAR(128) | NOT NULL | |
| `config` | JSONB | NOT NULL, DEFAULT `{}` | temperature、base_url 等 |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Skill

##### ORM 表 `agent_skill`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `description` | TEXT | NULL | |
| `tool_ids` | JSONB | NOT NULL, DEFAULT `[]` | 绑定的 Tool id |
| `prompt_template` | TEXT | NULL | 技能级提示 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Tool

##### ORM 表 `agent_tool`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `kind` | VARCHAR(16) | NOT NULL | `builtin` / `http` / `mcp` |
| `schema` | JSONB | NOT NULL | JSON Schema 参数定义 |
| `config` | JSONB | NOT NULL, DEFAULT `{}` | HTTP URL、handler 路径等 |
| `mcp_server_id` | UUID | FK → `agent_mcp_server.id`, NULL | `kind=mcp` 时 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Mcp Server

##### ORM 表 `agent_mcp_server`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `transport` | VARCHAR(16) | NOT NULL | `stdio` / `sse` |
| `config` | JSONB | NOT NULL | 命令行、URL、env |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Flow

##### ORM 表 `agent_flow`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `version` | INT | NOT NULL, DEFAULT 1 | 递增版本 |
| `profile_id` | UUID | FK → `agent_profile.id`, NOT NULL | |
| `definition` | JSONB | NOT NULL | `FlowDefinitionDocument`；`schema_version=1` 见序列化对象，`0` 为现网松散 dict |
| `status` | VARCHAR(16) | NOT NULL | `draft` / `published` / `archived` |
| `published_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (code, version)`。

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `agent:flow:compiled:{flow_id}:{version}` | STRING (JSON) | 3600s | 编译后图结构缓存 |

#### Beat Task

##### ORM 表 `agent_beat_task`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `flow_id` | UUID | FK → `agent_flow.id`, NOT NULL | |
| `cron` | VARCHAR(64) | NOT NULL | Celery Beat cron |
| `input_payload` | JSONB | NOT NULL, DEFAULT `{}` | 触发时注入 Run 的输入 |
| `is_enabled` | BOOLEAN | NOT NULL, DEFAULT true | |
| `last_triggered_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `agent:beat:lock:{beat_task_id}` | STRING | 任务周期 | 分布式锁，防 Beat 重复触发 |

说明：HTTP 管理面当前仅支持绑定 **工作流** `flow_id`。规划智能体定时见 `docs/plan/unreached/2026-08-20-规划智能体定时任务Beat-服务层应用层-修改.md`，本表暂不加 `profile_id`。

#### Resource Binding

##### ORM 表 `agent_resource_binding`

配置资源与 RBAC 主体的绑定。第 1 轮只落库，**不**按绑定过滤可见性、不调用 `PermissionService`。以后审核见 `docs/plan/unreached/2026-08-20-RBAC绑定可见性与管理员创建-服务层应用层-修改.md`。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `resource_type` | VARCHAR(16) | NOT NULL | `profile` / `skill` / `tool` / `mcp_server` |
| `resource_id` | UUID | NOT NULL | 对应配置表主键 |
| `subject_type` | VARCHAR(16) | NOT NULL | `organization` / `department` / `role` / `user` |
| `subject_id` | UUID | NOT NULL | 主体 id |
| `actions` | JSONB | NOT NULL | 如 `["read","use"]`；以后管理员用 `admin` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (resource_type, resource_id, subject_type, subject_id)`。索引：`idx_agent_resource_binding_resource (resource_type, resource_id)`。

创建 Profile / Skill / Tool / MCP 时同时写入 `sys_asset`：`asset_type` 同上，`asset_key` 为资源 UUID 字符串（改 `code` 不影响授权键）。`agent_profile.owner_organization_id` **不是** ACL，列保留。

#### Checkpoint Schema

##### ORM 表 `agent_checkpoint_schema`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `flow_id` | UUID | FK → `agent_flow.id`, NOT NULL | |
| `version` | INT | NOT NULL | 与 flow version 对齐 |
| `state_schema` | JSONB | NOT NULL | 由图定义 `GraphStateSpec` 生成的 JSON Schema（仅三槽） |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

说明：LangGraph 实际 checkpoint **字节**由 Postgres checkpointer 表存储（框架管理）；本表仅记录业务侧三槽说明。不开放第四个顶层通道；`variables` 内层键可由 `GraphStateSpec.channels[name=variables].json_schema` 约束。

### 可运行对象

#### Flow Runtime（已编译图 / LangGraph 图实例）

##### 类 `FlowRuntime`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `flow_id` | UUID | 来源配置 |
| `graph` | `CompiledGraph` | LangGraph 编译结果 |
| `checkpointer` | Postgres checkpointer | 框架提供 |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `compile()` | `FlowDefinitionDocument` | `FlowRuntime` | 从定义构建图；`schema_version=1` 为规范形态，`0` 由后续 runtime 双读 |
| `invoke()` | `RunStatePayload` | `RunStatePayload` | 同步单步调试 |
| `astream_events()` | `RunStatePayload`, `config` | `AsyncIterator[SseEvent]` | 生产流式事件 |

#### Tool Executor

##### 类 `ToolExecutor`

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `execute()` | `ToolCallRequest` | `ToolCallResult` | 按 `agent_tool.kind` 分发 |

#### Skill Runtime

##### 类 `SkillRuntime`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `skill_id` | UUID | |
| `tools` | `list[ToolExecutor]` | 绑定的工具执行器 |

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `invoke()` | `SkillInvokePayload` | `SkillInvokePayload` | 组装 prompt 并调用工具链 |

#### Mcp Client Session

##### 类 `McpClientSession`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `server_id` | UUID | `agent_mcp_server.id` |
| `_client` | MCP 客户端 | 进程内连接 |

| 方法 | 说明 |
| --- | --- |
| `connect()` / `close()` | 生命周期 |
| `call_tool(name, arguments)` | 远程工具调用 |

### 序列化对象

图描述同时服务两件事：**编译** `StateGraph`（只读 `state` / `nodes` / `edges` / `branches`），以及**画布展示**（另读 `view`）。拓扑只存在边与分支上；节点不保存邻接或层级。`entry_point` 与 `interrupt_before` 不是作者字段：入口由唯一 `start` 推导，HITL 中断点由 `hitl` 节点在编译期派生。

#### Flow Definition Document

##### Pydantic `FlowDefinitionDocument`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | `1` 为本节结构；`0` 见本节兼容表 |
| `state` | `GraphStateSpec` | 声明三槽及 reducer，不含一次运行的值 |
| `nodes` | list[`FlowNode`] | 恰一个 `type=start`，至少一个 `type=end` |
| `edges` | list[`FlowEdge`] | 无条件边，端点均为节点 id（或 `__end__`） |
| `branches` | list[`FlowBranch`] | 条件扇出；循环用回边 + 退出谓词，无独立 loop 边类型 |
| `view` | `FlowView` | NULL | 画布；`compile` 必须忽略 |

发布校验：边/分支端点存在；`subgraph.flow_code` 指向 `published` 且编译期无 Flow 代码互引用环；运行期回边允许，靠 `max_visits`。禁止在 JSON 内嵌可执行代码。

##### Pydantic `GraphStateSpec`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `channels` | list[`StateChannelSpec`] | **恰好三条**，`name` 不可增删 |

##### Pydantic `StateChannelSpec`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | Literal[`messages`, `variables`, `metadata`] | 顶层通道；不开放第四槽 |
| `reducer` | Literal[`append`, `merge`] | `messages` 必须 `append`；另两槽必须 `merge` |
| `json_schema` | dict | NULL | 仅 `variables` 可填，约束**内层键**，不是新顶层通道 |

父子图均为三槽；差异只在 `variables` 的 `json_schema` 与 `input_map` / `output_map` 路径（`messages` / `variables.*` / `metadata.*`）。

##### 兼容 `schema_version=0`（现网，后续 runtime 双读）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | list[dict] | `{id, kind, prompt}`；`kind` 为 `passthrough` / `interrupt` / `llm` |
| `edges` | list[dict] | `{source, target}`；`target` 可为 `END` / `__end__` / `end` |
| `entry_point` | str | 入口节点 id |
| `interrupt_before` | list[str] | 编译参数；version `1` 由 `hitl` 派生 |

#### Flow Node

##### Enum `NodeType`

| type | 名称 | 编译意图 |
| --- | --- | --- |
| `start` | 开始 | `add_edge(START, 后继)`；`inject` 在入图前写入三槽 |
| `end` | 结束 | `add_edge(该点, END)` |
| `llm` | 大模型推理 | 现网 llm 节点 |
| `tool` | 工具调用 | 节点内 `ToolExecutor` |
| `assign` | 状态赋值 | 替代「边上改 state」；只写 `variables.*` / `metadata.*` |
| `hitl` | HITL | `interrupt()`，派生 `interrupt_before` |
| `subgraph` | 子图 | **独立三槽 State + 新 Celery Run**；父留 checkpoint 后释放，见 Workflow 域 |
| `custom` | 自定义 | 注册表 `handler_key`；现网 `passthrough` 映射为 `passthrough` |

##### Pydantic `FlowNode`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | 文档内唯一；观测 / checkpoint / 画布稳定键 |
| `type` | `NodeType` | discriminator |
| `title` | str | NULL | 仅展示 |
| `data` | 随 `type` 的对象 | 禁止 `str`；见下列模型 |

##### Pydantic `StartNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `inject` | list[`InjectSpec`] | 声明从运行上下文写入哪条通道；**不**保存会话快照、时间戳、cron（cron 在 `agent_beat_task`） |

##### Pydantic `InjectSpec`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source` | Literal[`run`, `user`, `conversation`, `beat`, `clock`] | 运行时注入源 |
| `channel` | Literal[`messages`, `variables`, `metadata`] | 目标顶层槽 |
| `key` | str | NULL | `variables` / `metadata` 的内层键；写入 `messages` 时为空 |

##### Pydantic `EndNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `output_channels` | list[Literal[`messages`, `variables`, `metadata`]] | 写入本 Run `output_payload` 的槽；不描述进程资源回收 |

##### Pydantic `LlmNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `llm_ref` | str | `agent_llm.code` |
| `system_prompt` | str | NULL | 覆盖 Profile 系统提示 |
| `stream` | bool | 默认 true |

##### Pydantic `ToolNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tool_code` | str | `agent_tool.code` |
| `arguments_from` | dict[str, str] | 参数名 → state 路径 |
| `output_to` | str | 写入路径，须为 `variables.*` |

##### Pydantic `AssignNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `assignments` | list[`AssignOp`] | 边不承担 transform |

##### Pydantic `AssignOp`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `target` | str | `variables.*` 或 `metadata.*` |
| `expr` | str | 从当前三槽取值的表达式（实现轮再定语法） |

##### Pydantic `HitlNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `prompt_template` | str | |
| `form_schema` | dict | NULL | 待办表单 JSON Schema |
| `on_reject` | Literal[`fail`, `route`] | `fail` 结束 Run；`route` 走 `hitl_decision` 分支 |

##### Pydantic `SubgraphNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `flow_code` | str | 目标 Flow `code` |
| `version` | int | NULL | 空则取该 code 当前 published |
| `input_map` | list[`StateMapEntry`] | 父三槽 → 子 `RunStatePayload` |
| `output_map` | list[`StateMapEntry`] | 子结果 → 父三槽；可覆盖默认 `__subgraph__` 键 |
| `timeout_seconds` | int | NULL | 等待上限；到点取消子并把 `timeout` 回传父 |

定义中不展开子节点。画布下钻读取目标 Flow 的 `definition.view`。禁止同进程嵌套 compile。

##### Pydantic `StateMapEntry`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `from_path` | str | 源路径，如 `variables.foo`、`messages` |
| `to_path` | str | 目标路径，同规则 |

##### Pydantic `CustomNodeData`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `handler_key` | str | worker 注册表键，禁止内嵌 Python |
| `config` | dict | NOT NULL, DEFAULT `{}` | 静态配置 |

#### Flow Edge and Branch

无条件边只路由、不更新 state。条件路由是一个源点扇出到多个终点，不是「一条边一个终点」。循环是指向上游的 `FlowEdge` 或 `cases[].target`，退出写在同一 `FlowBranch`。

##### Pydantic `FlowEdge`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | |
| `source` | str | 节点 id |
| `target` | str | 节点 id 或 `__end__` |
| `label` | str | NULL | 仅展示 |

##### Pydantic `FlowBranch`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | |
| `source` | str | 单一源节点 |
| `router` | `BranchRouter` | 编译为 `add_conditional_edges` 的 path |
| `cases` | list[`BranchCase`] | `key` 与 path 返回值对应 |
| `default_target` | str | NULL | 未命中 |
| `max_visits` | int | NULL | 回边访问上限；超限走 `default_target` 或失败 |

##### Pydantic `BranchRouter`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `kind` | Literal[`state_path`, `expr`, `hitl_decision`, `child_status`] | |
| `path` | str | NULL | `kind=state_path` 时的三槽路径 |
| `expr` | str | NULL | `kind=expr` |

`child_status` 读取该源 `subgraph` 节点写入的 `SubgraphNodeResult.status`（`completed` / `failed` / `cancelled` / `timeout`）。

##### Pydantic `BranchCase`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | str | |
| `target` | str | 节点 id 或 `__end__` |

#### Flow View（仅表示层）

##### Pydantic `FlowView`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | dict[str, `NodeLayout`] | `id →` 坐标 |
| `edges` | dict[str, `EdgeLayout`] | 锚点 / 折线 |
| `branches` | dict[str, `EdgeLayout`] | 同边布局 |
| `groups` | list[dict] | NULL | 画布分组，无编译语义 |
| `computed_levels` | dict[str, int] | NULL | BFS 层级缓存；以逻辑图为准，保存前可重算 |

##### Pydantic `NodeLayout`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `x` | float | |
| `y` | float | |
| `w` | float | NULL | |
| `h` | float | NULL | |
| `z` | int | NULL | |

##### Pydantic `EdgeLayout`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `waypoints` | list[list[float]] | NULL | `[[x,y], ...]` |
| `color` | str | NULL | |

#### Tool Call Request / Result

##### Pydantic `ToolCallRequest`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tool_call_id` | str | |
| `tool_code` | str | |
| `arguments` | dict[str, Any] | |

##### Pydantic `ToolCallResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tool_call_id` | str | |
| `success` | bool | |
| `output` | Any | NULL |
| `error` | str | NULL |

#### Skill Invoke Payload

##### Pydantic `SkillInvokePayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `skill_code` | str | |
| `user_input` | str | |
| `context` | dict[str, Any] | |
| `tool_results` | list[ToolCallResult] | NULL |

#### Beat Task Trigger Payload

##### Pydantic `BeatTaskTriggerPayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `beat_task_id` | UUID | |
| `flow_id` | UUID | |
| `input_payload` | dict[str, Any] | |
| `scheduled_at` | datetime | |

---

## Workflow Execution and Scheduling

Run / Thread / Checkpoint Instance **之间无表字段外键**，由调度与运行时代码持有引用。持久化快照用于防丢与 HITL / Beat / **子图等待**续跑。

### 数据

#### Run Snapshot（执行结果防丢、续跑现场）

##### ORM 表 `wf_run_snapshot`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 即 Run 的运行时 id |
| `flow_id` | UUID | NOT NULL | 逻辑引用 `agent_flow.id` |
| `conversation_id` | UUID | NULL | 逻辑引用 `conv_conversation.id` |
| `user_id` | UUID | NOT NULL | 触发用户 |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `running` / `interrupted` / `waiting_child` / `completed` / `failed` / `cancelled` |
| `input_payload` | JSONB | NOT NULL | 启动输入 |
| `output_payload` | JSONB | NULL | 最终结果 |
| `error_message` | TEXT | NULL | |
| `thread_id` | UUID | NOT NULL | 关联 Thread 快照 id |
| `langgraph_thread_id` | VARCHAR(128) | NOT NULL | 传给 checkpointer 的 thread id |
| `started_at` | TIMESTAMPTZ | NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_wf_run_user (user_id, created_at DESC)`、`idx_wf_run_conv (conversation_id)`。

#### Thread Snapshot（调度上下文、并发归属现场）

##### ORM 表 `wf_thread_snapshot`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | Thread 运行时 id |
| `worker_id` | VARCHAR(128) | NULL | Celery worker 标识 |
| `queue_name` | VARCHAR(64) | NOT NULL | RabbitMQ 队列 |
| `priority` | INT | NOT NULL, DEFAULT 0 | |
| `context_payload` | JSONB | NOT NULL, DEFAULT `{}` | 调度上下文 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Hitl Pending（人机中断待办与恢复载荷）

##### ORM 表 `wf_hitl_pending`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `run_id` | UUID | NOT NULL | 逻辑引用 `wf_run_snapshot.id` |
| `node_id` | VARCHAR(128) | NOT NULL | 中断节点 |
| `prompt` | TEXT | NOT NULL | 呈现给用户的待办说明 |
| `resume_payload` | JSONB | NULL | 用户提交后的恢复输入 |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `approved` / `rejected` / `expired` |
| `expires_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `resolved_at` | TIMESTAMPTZ | NULL | |

#### Child Run Pending（子图独立 Run 等待；不复用 HITL 表）

父 worker 执行到 `subgraph` 节点：按 `input_map` 从父三槽构造子 `RunStatePayload`，`start` 子 Run（独立 `langgraph_thread_id`），父对该节点挂起（checkpoint 已在 PG），当前 Celery 任务结束，父 snapshot 置 `waiting_child`。

##### ORM 表 `wf_child_run_pending`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `parent_run_id` | UUID | NOT NULL | 逻辑引用父 `wf_run_snapshot.id` |
| `child_run_id` | UUID | NOT NULL | 逻辑引用子 Run |
| `node_id` | VARCHAR(128) | NOT NULL | 父图 `subgraph` 节点 id |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `resumed` / `parent_cancelled` |
| `timeout_at` | TIMESTAMPTZ | NULL | 来自 `SubgraphNodeData.timeout_seconds` |
| `resume_payload` | JSONB | NULL | `SubgraphNodeResult` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `resolved_at` | TIMESTAMPTZ | NULL | |

索引：`idx_wf_child_parent (parent_run_id)`、`idx_wf_child_child (child_run_id)` UNIQUE、`idx_wf_child_timeout (timeout_at)` WHERE `status = 'pending'`。

##### 超时 / 取消 / 完成回传

| 事件 | 子 Run | 父 Run |
| --- | --- | --- |
| 子 `completed` / `failed` | 保持该终态 | 组装 `SubgraphNodeResult`，`output_map` 写入父三槽后 `resume` |
| 子超时（`timeout_at`） | **取消子**（`cancelled`） | **不取消父**；`status=timeout` 作为子输出 resume 父 |
| 取消子（管理台/API） | **取消子** | **不取消父**；`status=cancelled` 作为子输出 resume 父 |
| 取消父 | 级联取消所有未完成子 | 父 `cancelled`，pending 置 `parent_cancelled`，**不再 resume** |

超时由 Beat（或与 `expire_hitl_pending` 同类的过期任务）扫描 `timeout_at`。`SubgraphNodeResult.output` 在超时/取消时取取消瞬间 hydrate 的子三槽；没有 checkpoint 则为空三槽。默认把整份结果写入父 `variables.__subgraph__.{node_id}`，再应用 `output_map`。

#### Celery Task Record（队列任务与 worker 认领记录）

##### ORM 表 `wf_celery_task_record`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `celery_task_id` | VARCHAR(128) | UNIQUE, NOT NULL | Celery 任务 id |
| `run_id` | UUID | NOT NULL | 逻辑引用 `wf_run_snapshot.id` |
| `task_name` | VARCHAR(128) | NOT NULL | 如 `run_langgraph_flow` |
| `status` | VARCHAR(16) | NOT NULL | `queued` / `started` / `retry` / `success` / `failure` |
| `retry_count` | INT | NOT NULL, DEFAULT 0 | |
| `worker_id` | VARCHAR(128) | NULL | |
| `queued_at` | TIMESTAMPTZ | NOT NULL | |
| `started_at` | TIMESTAMPTZ | NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `wf:run:active:{run_id}` | HASH | 随 run 生命周期 | 热状态：status、last_event_at |
| `wf:hitl:notify:{hitl_id}` | STRING | 至 expires_at | 待办提醒去重 |
| `wf:child:pending:{pending_id}` | STRING | 至 timeout_at | 子图等待去重 / 过期扫描辅助 |

### 可运行对象

#### Run（性能调度单位）

##### 类 `Run`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 与 `wf_run_snapshot.id` 同 id |
| `flow_runtime` | `FlowRuntime` | 引用 |
| `thread` | `Thread` | 引用 |
| `checkpoint_instance` | `CheckpointInstance` | NULL | 当前图状态内存对象 |
| `_snapshot` | RunSnapshot ORM | 持久化镜像 |

##### 运行方法

| 方法 | 说明 |
| --- | --- |
| `start()` | 写 snapshot `running`，提交 Celery |
| `resume(hitl: HitlResumeInput)` | HITL 恢复 |
| `resume_child(result: SubgraphNodeResult)` | 子图回传后恢复父（含 timeout / cancelled） |
| `cancel()` | 取消本 Run；若存在未完成子 pending 则级联取消子 |
| `persist()` | 将内存状态 flush 到 `wf_run_snapshot` |

#### Thread（性能调度单位）

##### 类 `Thread`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 与 `wf_thread_snapshot.id` 同 id |
| `langgraph_thread_id` | str | checkpointer 键 |
| `_snapshot` | ThreadSnapshot ORM | |

##### 运行方法

| 方法 | 说明 |
| --- | --- |
| `bind_worker(worker_id)` | 认领 worker |
| `persist()` | flush 调度上下文 |

#### Checkpoint Instance（从 Postgres checkpointer 读出的图状态内存对象）

##### 类 `CheckpointInstance`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `thread_id` | str | LangGraph thread |
| `state` | dict[str, Any] | 当前 state 字典 |
| `checkpoint_id` | str | 框架 checkpoint id |

##### 运行方法

| 方法 | 说明 |
| --- | --- |
| `load(checkpointer, thread_id)` | 从 PG 读出 hydrate |
| `apply_delta(delta)` | 合并节点输出 |
| `save(checkpointer)` | 写回 PG（委托 LangGraph） |

### 序列化对象

#### Run State Payload

##### Pydantic `RunStatePayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messages` | list[dict] | 顶层通道；reducer=`append` |
| `variables` | dict[str, Any] | 顶层通道；reducer=`merge`；业务扩展只进本槽 |
| `metadata` | dict[str, Any] | 顶层通道；reducer=`merge` |

不增加第四个顶层字段。子图同样使用本结构作为独立 State。

#### Subgraph Node Result

##### Pydantic `SubgraphNodeResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | Literal[`completed`, `failed`, `cancelled`, `timeout`] | 还给父的子终态 |
| `output` | `RunStatePayload` | 子三槽快照；超时/取消见上表 |
| `error` | str | NULL | 仅 `failed` |

#### Thread Context Payload

##### Pydantic `ThreadContextPayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `queue_name` | str | |
| `priority` | int | |
| `worker_affinity` | str | NULL | 亲和 worker |

#### Hitl Resume Input / Output

##### Pydantic `HitlResumeInput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `hitl_id` | UUID | |
| `decision` | Literal[`approve`, `reject`] | |
| `user_input` | str | NULL | 补充输入 |

##### Pydantic `HitlResumeOutput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | UUID | |
| `resumed` | bool | |

#### Celery Task Envelope

##### Pydantic `CeleryTaskEnvelope`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_name` | str | |
| `run_id` | UUID | |
| `flow_id` | UUID | |
| `thread_id` | UUID | |
| `langgraph_thread_id` | str | |
| `input_payload` | RunStatePayload | |

---

## Knowledge, Files and Retrieval Index

原文在 MinIO；**Knowledge Chunk** 为向量（pgvector）与全文（tsvector + zhparser）对齐 id；应用层 RRF 融合后由 Celery worker 内 ONNX 重排。领域图见 Graph Knowledge。

### 数据

#### Knowledge Collection

##### ORM 表 `kb_collection`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 知识库集合 |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | 稳定标识 |
| `name` | VARCHAR(128) | NOT NULL | 展示名 |
| `description` | TEXT | NULL | |
| `owner_organization_id` | UUID | NULL | 多租户 |
| `embedding_model` | VARCHAR(128) | NOT NULL | 向量模型标识 |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT `active` | `active` / `archived` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Knowledge Doc

##### ORM 表 `kb_doc`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 文档 |
| `collection_id` | UUID | FK → `kb_collection.id`, NOT NULL | |
| `title` | VARCHAR(512) | NOT NULL | |
| `source_type` | VARCHAR(32) | NOT NULL | `upload` / `url` / `api` |
| `source_uri` | VARCHAR(1024) | NULL | 原始来源 |
| `storage_object_id` | UUID | FK → `file_storage_object.id`, NULL | MinIO 原文 |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `indexed` / `failed` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_kb_doc_collection (collection_id)`。

#### Knowledge Section

##### ORM 表 `kb_section`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 章节/逻辑分段 |
| `doc_id` | UUID | FK → `kb_doc.id`, NOT NULL | |
| `ordinal` | INT | NOT NULL | 文档内顺序 |
| `heading` | VARCHAR(512) | NULL | 标题 |
| `char_start` | INT | NOT NULL | 在原文中的起始偏移 |
| `char_end` | INT | NOT NULL | 结束偏移 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Knowledge Chunk

##### ORM 表 `kb_chunk`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | chunk id，向量/全文/MinIO 对齐键 |
| `collection_id` | UUID | FK → `kb_collection.id`, NOT NULL | |
| `doc_id` | UUID | FK → `kb_doc.id`, NOT NULL | |
| `section_id` | UUID | FK → `kb_section.id`, NULL | |
| `ordinal` | INT | NOT NULL | chunk 序号 |
| `content` | TEXT | NOT NULL | 切片文本 |
| `content_tsv` | TSVECTOR | GENERATED | 全文索引列（zhparser） |
| `embedding` | VECTOR(n) | NULL | pgvector；n 与模型维度一致 |
| `token_count` | INT | NOT NULL | |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | 页码、表格标记等 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_kb_chunk_collection (collection_id)`、`idx_kb_chunk_embedding USING ivfflat (embedding vector_cosine_ops)`（按需）、`idx_kb_chunk_tsv USING GIN (content_tsv)`。

#### Ingestion Job

##### ORM 表 `kb_ingestion_job`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `collection_id` | UUID | FK → `kb_collection.id`, NOT NULL | |
| `doc_id` | UUID | FK → `kb_doc.id`, NULL | 单文档任务 |
| `trigger` | VARCHAR(16) | NOT NULL | `manual` / `upload` / `reindex` |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `running` / `success` / `failed` |
| `stats` | JSONB | NOT NULL, DEFAULT `{}` | `{"chunks":120,"embedded":120}` |
| `error_message` | TEXT | NULL | |
| `started_at` | TIMESTAMPTZ | NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `kb:ingest:lock:{doc_id}` | STRING | 3600s | 防重复入库 |
| `kb:ingest:progress:{job_id}` | HASH | 3600s | 进度热读 |

#### File

##### ORM 表 `file_record`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | 业务文件记录 |
| `name` | VARCHAR(512) | NOT NULL | 逻辑文件名 |
| `mime_type` | VARCHAR(128) | NOT NULL | |
| `owner_user_id` | UUID | FK → `sys_user.id`, NOT NULL | |
| `purpose` | VARCHAR(32) | NOT NULL | `knowledge` / `artifact` / `attachment` |
| `current_version_id` | UUID | NULL | 逻辑引用 `file_version.id` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Storage Object

##### ORM 表 `file_storage_object`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `bucket` | VARCHAR(64) | NOT NULL | MinIO bucket |
| `object_key` | VARCHAR(1024) | NOT NULL | S3 key |
| `etag` | VARCHAR(128) | NULL | |
| `size_bytes` | BIGINT | NOT NULL | |
| `checksum_sha256` | VARCHAR(64) | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (bucket, object_key)`。

#### File Version

##### ORM 表 `file_version`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `file_id` | UUID | FK → `file_record.id`, NOT NULL | |
| `version_no` | INT | NOT NULL | 从 1 递增 |
| `storage_object_id` | UUID | FK → `file_storage_object.id`, NOT NULL | |
| `created_by` | UUID | FK → `sys_user.id`, NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (file_id, version_no)`。

#### Upload Session

##### ORM 表 `file_upload_session`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `user_id` | UUID | FK → `sys_user.id`, NOT NULL | |
| `file_name` | VARCHAR(512) | NOT NULL | |
| `mime_type` | VARCHAR(128) | NOT NULL | |
| `total_size` | BIGINT | NOT NULL | |
| `uploaded_size` | BIGINT | NOT NULL, DEFAULT 0 | |
| `storage_object_id` | UUID | NULL | 完成后绑定 |
| `status` | VARCHAR(16) | NOT NULL | `initiated` / `uploading` / `completed` / `aborted` |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `file:upload:parts:{session_id}` | SET | 至 expires_at | 已上传分片序号 |

### 可运行对象

#### Ingestion Pipeline

##### 类 `IngestionPipeline`

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | UUID | 对应 `kb_ingestion_job` |
| `doc_id` | UUID | |

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `run()` | — | `IngestionJobStats` | Celery 任务入口 |
| `fetch_raw()` | — | `bytes` | 从 MinIO 读原文 |
| `parse()` | `bytes` | `ChunkParseResult` | 解析为 Section + Chunk |
| `embed()` | `EmbeddingInput` | `EmbeddingOutput` | 批量写 pgvector |
| `index_fulltext()` | `list[ChunkRef]` | — | 更新 tsvector |

#### Retrieval Service

##### 类 `RetrievalService`

##### 运行方法

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `search()` | `SearchQuery` | `SearchHitList` | 向量 + 全文双路召回 |
| `fuse()` | `SearchHitList` | `SearchHitList` | RRF 融合 |
| `rerank()` | `SearchHitList`, `query: str` | `RerankResult` | ONNX 交叉编码器重排 |

### 序列化对象

#### Chunk Parse Result

##### Pydantic `ChunkParseResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sections` | list[SectionDraft] | `heading, char_start, char_end` |
| `chunks` | list[ChunkDraft] | `content, ordinal, metadata` |

#### Embedding Input / Output

##### Pydantic `EmbeddingInput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chunk_ids` | list[UUID] | |
| `texts` | list[str] | 与 ids 对齐 |
| `model` | str | |

##### Pydantic `EmbeddingOutput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `vectors` | list[list[float]] | |
| `dimensions` | int | |

#### Search Query

##### Pydantic `SearchQuery`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `collection_ids` | list[UUID] | |
| `query_text` | str | |
| `top_k` | int | 默认 20 |
| `filters` | dict[str, Any] | NULL | doc metadata 过滤 |

#### Search Hit / Rerank Result

##### Pydantic `SearchHit`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chunk_id` | UUID | |
| `doc_id` | UUID | |
| `score` | float | 单路分数 |
| `source` | Literal[`vector`, `fulltext`] | 召回来源 |
| `snippet` | str | |

##### Pydantic `RerankResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `hits` | list[SearchHit] | 重排后 |
| `model` | str | 重排模型名 |

#### Upload Part Descriptor

##### Pydantic `UploadPartDescriptor`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | UUID | |
| `part_number` | int | |
| `size` | int | |
| `checksum` | str | NULL | 分片校验 |

---

## Graph Knowledge

按需。领域图（知识、血缘、多跳），不承载 LangGraph 工作流。初期可用 Postgres 普通表；规模或信创需求再迁 Nebula / AGE。

### 数据

#### Graph Node

##### ORM 表 `graph_node`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `graph_key` | VARCHAR(64) | NOT NULL | 图命名空间，如 `kb_lineage` |
| `node_type` | VARCHAR(64) | NOT NULL | `entity` / `concept` / `doc` 等 |
| `external_ref` | VARCHAR(256) | NULL | 关联 `kb_doc.id` 等，逻辑引用 |
| `label` | VARCHAR(512) | NOT NULL | |
| `properties` | JSONB | NOT NULL, DEFAULT `{}` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (graph_key, node_type, external_ref)` WHERE `external_ref IS NOT NULL`。

#### Graph Edge

##### ORM 表 `graph_edge`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `graph_key` | VARCHAR(64) | NOT NULL | |
| `source_node_id` | UUID | FK → `graph_node.id`, NOT NULL | |
| `target_node_id` | UUID | FK → `graph_node.id`, NOT NULL | |
| `relation_type` | VARCHAR(64) | NOT NULL | `depends_on` / `mentions` 等 |
| `weight` | FLOAT | NULL | |
| `properties` | JSONB | NOT NULL, DEFAULT `{}` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_graph_edge_source (source_node_id)`、`idx_graph_edge_target (target_node_id)`。

#### Entity Link

##### ORM 表 `graph_entity_link`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `entity_name` | VARCHAR(256) | NOT NULL | 归一化实体名 |
| `node_id` | UUID | FK → `graph_node.id`, NOT NULL | |
| `confidence` | FLOAT | NOT NULL, DEFAULT 1.0 | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

唯一约束：`UNIQUE (entity_name, node_id)`。

### 可运行对象

#### Graph Query Service

##### 类 `GraphQueryService`

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `traverse()` | `GraphTraversalQuery` | `GraphQueryResult` | 多跳查询 |
| `shortest_path()` | `source_id`, `target_id`, `max_hops` | `GraphQueryResult` | |
| `neighbors()` | `node_id`, `relation_type?` | `GraphQueryResult` | 一跳 |

### 序列化对象

#### Graph Traversal Query

##### Pydantic `GraphTraversalQuery`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `graph_key` | str | |
| `start_node_ids` | list[UUID] | |
| `relation_types` | list[str] | NULL |
| `max_hops` | int | 默认 3 |
| `direction` | Literal[`out`, `in`, `both`] | |

#### Graph Query Result

##### Pydantic `GraphQueryResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | list[dict] | id, label, node_type, properties |
| `edges` | list[dict] | source, target, relation_type |
| `paths` | list[list[UUID]] | NULL | 路径列表 |

---

## Security and Rate Limit

内容护栏与接口限流；JWT 黑名单仍在 Permission。输出过滤在 LangGraph 输出节点调用，不占 FastAPI 中间件。

### 数据

#### Guardrail Rule

##### ORM 表 `sec_guardrail_rule`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `code` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `stage` | VARCHAR(16) | NOT NULL | `input` / `output` |
| `rule_type` | VARCHAR(32) | NOT NULL | `jailbreak` / `pii` / `keyword` |
| `config` | JSONB | NOT NULL | 规则参数 |
| `is_enabled` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Policy Violation

##### ORM 表 `sec_policy_violation`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `rule_id` | UUID | FK → `sec_guardrail_rule.id`, NOT NULL | |
| `user_id` | UUID | NULL | |
| `run_id` | UUID | NULL | 逻辑引用 wf run |
| `conversation_id` | UUID | NULL | |
| `stage` | VARCHAR(16) | NOT NULL | |
| `matched_excerpt` | TEXT | NULL | 脱敏后的匹配片段 |
| `action_taken` | VARCHAR(16) | NOT NULL | `block` / `mask` / `log` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Rate Limit Bucket（Redis）

##### Redis Key 定义

| Key 模式 | 类型 | TTL | Value | 说明 |
| --- | --- | --- | --- | --- |
| `sec:ratelimit:{scope}:{subject}:{window}` | STRING | 窗口长度 | 计数 | scope 如 `api`/`llm`；subject 如 user_id |
| `sec:ratelimit:cfg:{scope}` | HASH | 长期 | limit, window_seconds | 限流配置热读 |

### 可运行对象

#### Guardrail Evaluator

##### 类 `GuardrailEvaluator`

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `check_input()` | `GuardrailCheckInput` | `GuardrailCheckOutput` | 图入口 |
| `check_output()` | `GuardrailCheckInput` | `GuardrailCheckOutput` | 图出口；流式逐块累积 |

#### Rate Limiter

##### 类 `RateLimiter`

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `allow()` | `scope`, `subject_id` | `RateLimitDecision` | 原子 INCR + EXPIRE |
| `reset()` | `scope`, `subject_id` | — | 管理用 |

### 序列化对象

#### Guardrail Check Input / Output

##### Pydantic `GuardrailCheckInput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `text` | str | 待检文本 |
| `stage` | Literal[`input`, `output`] | |
| `context` | dict[str, Any] | NULL | run_id 等 |

##### Pydantic `GuardrailCheckOutput`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `passed` | bool | |
| `action` | Literal[`allow`, `block`, `mask`] | |
| `masked_text` | str | NULL | |
| `violated_rule_codes` | list[str] | |

#### Rate Limit Decision

##### Pydantic `RateLimitDecision`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `allowed` | bool | |
| `limit` | int | |
| `remaining` | int | |
| `reset_at` | datetime | |

---

## Audit and Usage

业务侧获取/消耗与操作日志；与 Permission `Quota` 计数配合；推理明细见 Observability。

### 数据

#### Asset Obtain

##### ORM 表 `audit_asset_obtain`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `subject_type` | VARCHAR(16) | NOT NULL | `user` / `organization` / `role` |
| `subject_id` | UUID | NOT NULL | |
| `quota_type` | VARCHAR(32) | NOT NULL | 与 `sys_quota.quota_type` 一致 |
| `amount` | BIGINT | NOT NULL | 获得量 |
| `reason` | VARCHAR(128) | NOT NULL | `grant` / `purchase` / `adjust` |
| `operator_id` | UUID | NULL | |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Asset Consume

##### ORM 表 `audit_asset_consume`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `subject_type` | VARCHAR(16) | NOT NULL | |
| `subject_id` | UUID | NOT NULL | |
| `quota_type` | VARCHAR(32) | NOT NULL | |
| `amount` | BIGINT | NOT NULL | 消耗量 |
| `source` | VARCHAR(32) | NOT NULL | `llm_call` / `api` / `storage` |
| `run_id` | UUID | NULL | 逻辑引用 |
| `conversation_id` | UUID | NULL | |
| `metadata` | JSONB | NOT NULL, DEFAULT `{}` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_audit_consume_subject (subject_type, subject_id, created_at DESC)`。

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `auth:quota:{subject_type}:{subject_id}:{quota_type}:{period}` | STRING | 与 period 对齐 | 由 consume 异步累加，与 Permission Quota 热读一致 |

#### Activity

##### ORM 表 `audit_activity`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `user_id` | UUID | FK → `sys_user.id`, NULL | |
| `action` | VARCHAR(64) | NOT NULL | `login` / `flow.publish` / `kb.upload` 等 |
| `resource_type` | VARCHAR(32) | NULL | |
| `resource_id` | UUID | NULL | |
| `ip_address` | INET | NULL | |
| `user_agent` | VARCHAR(512) | NULL | |
| `detail` | JSONB | NOT NULL, DEFAULT `{}` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

索引：`idx_audit_activity_user (user_id, created_at DESC)`。

### 可运行对象

（无）

### 序列化对象

#### Audit Event Envelope

##### Pydantic `AuditEventEnvelope`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `action` | str | |
| `user_id` | UUID | NULL |
| `resource_type` | str | NULL |
| `resource_id` | UUID | NULL |
| `detail` | dict[str, Any] | |
| `occurred_at` | datetime | |

#### Usage Meter Reading

##### Pydantic `UsageMeterReading`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `subject_type` | str | |
| `subject_id` | UUID | |
| `quota_type` | str | |
| `period` | str | |
| `used` | int | |
| `limit` | int | |

---

## Observability and Trace

OpenTelemetry 采链路；LangFuse 记 prompt / token / 工具调用。Prompt 入库前脱敏；可与 `run_id` 逻辑关联，**不做 trace 表对 run 的外键**。

### 数据

#### Trace

##### ORM 表 `obs_trace`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `trace_id` | VARCHAR(64) | UNIQUE, NOT NULL | OTel trace id |
| `run_id` | UUID | NULL | 逻辑引用 |
| `conversation_id` | UUID | NULL | |
| `user_id` | UUID | NULL | |
| `name` | VARCHAR(128) | NOT NULL | 如 `langgraph.run` |
| `status` | VARCHAR(16) | NOT NULL | `ok` / `error` |
| `started_at` | TIMESTAMPTZ | NOT NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Span

##### ORM 表 `obs_span`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `trace_id` | VARCHAR(64) | NOT NULL | 逻辑关联 `obs_trace.trace_id` |
| `span_id` | VARCHAR(64) | UNIQUE, NOT NULL | |
| `parent_span_id` | VARCHAR(64) | NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `kind` | VARCHAR(16) | NOT NULL | `internal` / `client` / `server` |
| `attributes` | JSONB | NOT NULL, DEFAULT `{}` | |
| `started_at` | TIMESTAMPTZ | NOT NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |
| `duration_ms` | INT | NULL | |

#### Llm Call

##### ORM 表 `obs_llm_call`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `span_id` | VARCHAR(64) | NOT NULL | |
| `run_id` | UUID | NULL | |
| `model` | VARCHAR(128) | NOT NULL | |
| `prompt_tokens` | INT | NOT NULL | |
| `completion_tokens` | INT | NOT NULL | |
| `latency_ms` | INT | NOT NULL | |
| `status` | VARCHAR(16) | NOT NULL | |
| `error_message` | TEXT | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Tool Invocation

##### ORM 表 `obs_tool_invocation`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `span_id` | VARCHAR(64) | NOT NULL | |
| `run_id` | UUID | NULL | |
| `tool_code` | VARCHAR(64) | NOT NULL | |
| `latency_ms` | INT | NOT NULL | |
| `success` | BOOLEAN | NOT NULL | |
| `error_message` | TEXT | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### Prompt Snapshot

##### ORM 表 `obs_prompt_snapshot`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `llm_call_id` | UUID | FK → `obs_llm_call.id`, NOT NULL | |
| `role` | VARCHAR(16) | NOT NULL | `system` / `user` / `assistant` |
| `content_redacted` | TEXT | NOT NULL | 脱敏后内容 |
| `content_hash` | VARCHAR(64) | NOT NULL | 原文 SHA-256，便于去重审计 |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

### 可运行对象

#### Trace Collector

##### 类 `TraceCollector`

| 方法 | 说明 |
| --- | --- |
| `start_trace(name, context)` | 创建 OTel span |
| `end_trace(status)` | |
| `record_span(name, attributes)` | 子 span |
| `flush()` | 批量写 `obs_*` 表 |

#### Langfuse Reporter

##### 类 `LangfuseReporter`

| 方法 | 入参 | 说明 |
| --- | --- | --- |
| `report_generation()` | `LlmUsageMetrics` | 上报 generation |
| `report_tool()` | `ToolTraceRecord` | 上报 tool span |
| `shutdown()` | — | 刷缓冲 |

### 序列化对象

#### Span Attributes Payload

##### Pydantic `SpanAttributesPayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | UUID | NULL |
| `flow_id` | UUID | NULL |
| `node_id` | str | NULL |
| `extra` | dict[str, str] | OTel 属性 |

#### Llm Usage Metrics

##### Pydantic `LlmUsageMetrics`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `trace_id` | str | |
| `model` | str | |
| `prompt_tokens` | int | |
| `completion_tokens` | int | |
| `latency_ms` | int | |
| `cost_usd` | float | NULL |

#### Tool Trace Record

##### Pydantic `ToolTraceRecord`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `trace_id` | str | |
| `tool_code` | str | |
| `input_summary` | str | 脱敏摘要 |
| `output_summary` | str | NULL |
| `latency_ms` | int | |
| `success` | bool | |

---

## Notification

按需。工作流完成、HITL 待办、知识库入库完成等对外 Webhook。

### 数据

#### Webhook Endpoint

##### ORM 表 `notify_webhook_endpoint`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `owner_organization_id` | UUID | NULL | |
| `name` | VARCHAR(128) | NOT NULL | |
| `url` | VARCHAR(2048) | NOT NULL | HTTPS |
| `secret` | VARCHAR(128) | NOT NULL | 签名密钥 |
| `event_types` | JSONB | NOT NULL | 如 `["run.completed","hitl.pending"]` |
| `is_enabled` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### Delivery Log

##### ORM 表 `notify_delivery_log`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `endpoint_id` | UUID | FK → `notify_webhook_endpoint.id`, NOT NULL | |
| `event_type` | VARCHAR(64) | NOT NULL | |
| `payload_hash` | VARCHAR(64) | NOT NULL | 防重复 |
| `status` | VARCHAR(16) | NOT NULL | `pending` / `success` / `failed` |
| `http_status` | INT | NULL | |
| `response_body` | TEXT | NULL | 截断存储 |
| `attempt_count` | INT | NOT NULL, DEFAULT 0 | |
| `next_retry_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `finished_at` | TIMESTAMPTZ | NULL | |

##### Cache

| Key 模式 | 类型 | TTL | 说明 |
| --- | --- | --- | --- |
| `notify:dedupe:{endpoint_id}:{payload_hash}` | STRING | 86400s | 24h 内同载荷不重复投递 |

### 可运行对象

#### Webhook Dispatcher

##### 类 `WebhookDispatcher`

| 方法 | 入参 | 出参 | 说明 |
| --- | --- | --- | --- |
| `dispatch()` | `NotificationEventEnvelope` | `UUID` | 写 delivery_log，异步 HTTP |
| `retry_pending()` | — | `int` | Celery Beat 重试失败项 |
| `sign_payload()` | `WebhookDeliveryPayload`, `secret` | `str` | HMAC 签名头 |

### 序列化对象

#### Webhook Delivery Payload

##### Pydantic `WebhookDeliveryPayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` | UUID | |
| `event_type` | str | |
| `occurred_at` | datetime | |
| `data` | dict[str, Any] | 业务载荷 |

#### Notification Event Envelope

##### Pydantic `NotificationEventEnvelope`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_type` | Literal[`run.completed`, `run.failed`, `hitl.pending`, `kb.ingest.done`] | |
| `organization_id` | UUID | NULL |
| `resource_type` | str | |
| `resource_id` | UUID | |
| `payload` | dict[str, Any] | |
