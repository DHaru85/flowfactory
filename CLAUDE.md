# FlowFactory - An Agent Workflow Production Factory

## introduction

FlowFactory 是一个 **Agent 工作流生产工厂**：把 LangGraph 驱动的 Agent 工作流，从交互、编排、知识检索到持久化与观测，做成可上线、可恢复、可扩展的生产系统，而不是单次脚本或 Demo。

**功能目标**

- 提供 Web 管理台与会话界面，支持 Agent 流式输出、结构化结果展示，以及工作流相关后台操作。
- 按交互场景拆分**应用**，每个应用对应一类用户场景；底层**服务**可被多个应用复用，应用也可组合多个服务。
- 以 LangGraph 为核心运行 Agent 图：支持 checkpoint、中断、人在回路（HITL），长时 run 异步执行，失败可重试、状态可恢复。
- 内置知识检索链路：原文存对象存储，初期在 Postgres 上做向量 + 全文混合召回与重排；按需扩展 ES/Milvus 与领域图库。
- 提供鉴权、限流、可选内容护栏，以及 OpenTelemetry + LangFuse 全链路可观测，便于排障与成本核算。

## Structure
### abstract
工程总体可以分为以下几个部分，每个部分承担的职责和功能描述如下:

- **表示层**: 直接与人类进行交互的图形化前端界面；负责提供友好的交互界面和基于 Agent 产出内容构建的丰富响应结果展示
- **应用层**: 为表示层交互提供功能支持, 应用根据发生在前端界面中的各类交互场景归纳得到；一个应用通常只负责为某一类交互场景提供功能支持
- **服务层**: 为应用层的应用提供功能实现所必要的一切基础设施；负责支持应用层的功能逻辑正常运转，服务通常可以为多个应用提供基础设施保障，一个应用可能同时享受多个服务提供的功能支持
- **映射层**: 提供各个 应用/服务 在运转过程中所定义的数据结构与数据层存储的关系型数据/图数据/文档数据/对象存储数据之间存在的映射模型定义, 负责保证数据定义的一致性
- **数据层**: 为各个 应用/服务 的运转过程提供状态缓存/状态持久化支持；负责数据库连接池管理、数据操作事务管理

工程结构如下图所示:
```mermaid
flowchart TB
    subgraph Presentation["表示层"]
        WEB["Web 交互界面<br/>React + Vite"]
    end

    subgraph Application["应用层"]
        direction LR
        A1["应用 A<br/>一类交互场景"]
        A2["应用 B<br/>一类交互场景"]
    end

    subgraph ServiceLayer["服务层"]
        direction LR
        S1["服务 X"]
        S2["服务 Y"]
    end

    subgraph Mapping["映射层"]
        MAP["映射模型定义 · 保证数据定义一致性<br/>关系型 / 图数据 / 文档数据 / 对象存储"]
    end

    subgraph DataLayer["数据层"]
        direction LR
        Cache["状态缓存"]
        Persist["状态持久化"]
        Pool["连接池管理 / 事务管理"]
    end

    WEB -->|交互请求| A1
    WEB -->|交互请求| A2
    A1 -->|调用| S1
    A1 -->|调用| S2
    A2 -->|调用| S1
    A1 --> MAP
    A2 --> MAP
    S1 --> MAP
    S2 --> MAP
    MAP -->|读写| Cache
    MAP -->|读写| Persist
    Cache --- Pool
    Persist --- Pool
```

### technic selection table

工程各层所涉及的技术路线/组件选型见下表。**必选**为必要的组件；**按需**计划在出现明确约束或瓶颈的后续工程阶段再引入。

| 事项 | 选型结果 | 理由 |
| --- | --- | --- |
| 表示层技术栈主体 **必选** | React + Vite | SPA 将表示层与应用层分离；组件生态适合流式结果与复杂交互；Vite 只负责开发与构建 |
| 表示层 UI **必选** | Antd + Ant Design X（会话区） | Antd 管后台表单/表格/布局；会话区用 Ant Design X 或 `react-markdown` + Shiki 自研，对接自建 SSE 协议。不引入 Vercel AI SDK（偏 Next 数据流，与 FastAPI SSE 需额外适配） |
| 表示层与应用层交互 **必选** | 流式用 SSE，普通操作用 RESTful | Agent 下行是单向吐 token，SSE 走标准 HTTP、实现简单、易过网关；上行命令仍走 REST。WebSocket 的全双工在此用不上 |
| 应用层框架 **必选** | FastAPI | 与 LangGraph 同语言；async 适合等待 LLM；与 Pydantic 原生集成。持久化用 SQLAlchemy，不把 SQLModel 当作必选封装 |
| 鉴权 **必选** | JWT + Redis 记 `jti` | 网关可本地验签；登出、踢人、改密时用 Redis 黑名单作废未过期 token（TTL = 剩余有效期）。短 JWT + 刷新令牌 |
| 内容安全护栏 **按需** | LangGraph 节点钩子 + 独立策略服务 | 越狱/注入检测放在图入口节点；PII/敏感词过滤放在输出节点（SSE 流式场景中间件难以截断 token）。目标是降低风险，不承诺「绝对安全」。重型检测不占 FastAPI 入口 worker |
| 工作流执行 **必选** | Celery（prefork）+ RabbitMQ | FastAPI 只接短请求与 SSE；长 LangGraph run 进队列。Celery 负责任务提交、重试、定时与并发上限；prefork 隔离崩溃。LangGraph 的 checkpoint、中断、HITL 由 Postgres checkpointer 承担，不由 Celery 替代 |
| 工作流外层编排 **按需** | Temporal | 仅当出现跨天等待、图外系统补偿（支付/工单）、需信号唤醒的长 saga 时，用 Temporal 作**外层**编排（Activity 内跑 LangGraph），避免与图内 checkpoint 形成双状态机 |
| 缓存与热状态 **必选** | Redis | 限流、会话缓存、JWT `jti` 黑名单 |
| 对象存储 **必选** | MinIO | 对齐映射层的文件 / 产物对象存储；S3 协议，便于自建，上云可换官方 S3 |
| Agent 技术栈 **必选** | LangGraph 为主；LangChain 按需 | LangGraph 提供可恢复工作流（checkpoint、中断、人机协同）；LangChain 提供模型与工具适配。容错靠 Postgres checkpoint + Celery 重试；并发靠 RabbitMQ 队列深度与 worker 数 |
| 知识检索 **必选（初期）** | Postgres：`pgvector` + `tsvector`（`zhparser`） | 初期不拆 ES/Milvus：向量用 pgvector，词面全文用 tsvector + 中文分词（`pg_trgm` 只做模糊匹配，不能替代全文）。原文在 MinIO，chunk id 与索引对齐。应用层 RRF 融合两路召回 |
| 重排模型 **必选** | ONNX Runtime（跑在 Celery worker） | 交叉编码器重排提高 top-k 质量；放在图/检索 worker 进程，不占 FastAPI 事件循环 |
| 知识检索扩展 **按需** | Elasticsearch + Milvus | 词面召回或过滤聚合明显弱于 PG、或向量规模/ QPS 出现瓶颈时再拆。Milvus 与 Nebula 升级条件独立（向量规模 vs 图建模需求） |
| 主存储与 checkpoint **必选** | Postgres | 事务与数据层一致；JSONB 覆盖部分文档数据；LangGraph checkpoint 落在 Postgres，保证在途图可恢复 |
| 图数据存储 **按需** | Nebula / Postgres AGE | 只承载领域图（知识、血缘、多跳关系），不跑 LangGraph 工作流。信创/国产化选 Nebula；无约束且规模中小优先 AGE，少一套运维面 |
| 全链路可观测性 **必选** | OpenTelemetry + LangFuse | OTel 采集 HTTP/DB/队列/Temporal 链路；LangFuse 记录 prompt、token、工具调用与失败原因。Prompt 入库前脱敏，避免观测面本身泄漏 PII |

## engineering standard
### directory defination

```text
--- README.md                            # 项目总体说明文档
 |- CLAUDE.md                            # 项目总体说明的软链接，适 CLAUDE CODE
 |- AGENTS.md                            # 同CLAUDE.md，适用非 CLAUDE CODE 的 Vibe-Coding 应用
 |- docs                                 # 项目所有细节说明文档目录
    |- design                            # 在总体说明中定义的架构下进行的细节设计文档, 例如API接口设计、数据结构定义等
    |- construction                      # 模块施工状态文档
    |- plan                              # 施工方案文档
 |- docker                               # 容器化部署管理目录
    |- backend                           # 后端冷加载配置文件映射目录
    |- frontend                          # 前端 nginx 配置脚本映射目录
    |- postgres                          # 事实数据存储映射
    |- redis                             # 缓存的相关存储映射
    |- minio                             # 对象存储映射
    |- docker-compose.yml                # 构建栈定义（单机版）
    |- docker-compose-cloud.yml          # 构建栈定义（云版）
 |- scripts                              # 相关的脚本
    |- initial                           # 宿主机中适用
    |- container                         # 容器中适用
 |- src                                  # 工程源码
    |- backend                           # 后端建设
        |- api                           # 应用层建设
            |- app.py                    # FastAPI 实例
            |- routers                   # 路由函数定义包
        |- data_schema                   # ORM模型/数据结构定义（映射层实现）
        |- logs                          # 运行时日志
        |- service                       # 运行时基础设施（服务层）
        |- settings                      # 后端总体配置设置
        |- tests                         # 功能试验场
            |- unit                      # 针对部分功能的单元测试
            |- module                    # 针对一组模块功能的协作测试
        |- Dockerfile                    # 容器构建脚本
    |- frontend                          # 前端建设
        |- dist                          # build产物
        |- source                        # 源代码
        |- Dockerfile                    # 容器构建脚本
        |- vite.config.ts                # 配置
        |- vite.config.mts               # 另一种配置
```

### workflow defination
#### steps

当用户提出一个或一组新的需求待实现时，遵守以下工作流定义进行工作:
```mermaid
flowchart TB
    A[Start] --> B[确定本轮需求涉及的修改施工范围]
    B -->|施工范围在施工状态文档（docs/construction）中被定义为施工中| C[拒绝本次施工并且告知用户该区域施工中，等待上一轮施工结束再试]
    B -->|施工范围为空闲中| D[理解用户需求，编写施工方案，存放在（docs/plan）， 编写规范参考 `key points` 章节说明]
    D -->|用户需求明确，无待澄清事项| E[简介施工效果，等待用户确认]
    D -->|用户需求不明确| F[整理待澄清事项，向用户提问]
    E -->|用户确认| G[锁定施工方案文档，开始施工]
    E -->|用户拒绝| H[停止施工，保留施工方案]
    F -->|用户解答后需求明确| E
    F -->|用户解答后需求不明确| F
    G -->|工程顺利，没有衍生问题| I[施工结束后整理施工简报]
    G -->|工程受阻，有衍生问题| F
    I --> J[END]
    H --> J
```

#### key points

- **施工工作流程细则**:
    1. **先思考**: 在进行任何更改时都需要分析功能需求和项目现状，并且提交修改方案计划到 /docs/plan 目录下
    2. **拿不准的问用户**: 分析功能需求时发现不明确的需求，先和用户确认，澄清分歧，并记录用户他提出的功能需求和澄清过程在修改方案的首个章节里
    3. **严格执行**: 一旦完成修改方案的生成和澄清过程，修改方案中的任务要求和验收标准就是铁律，必须严格遵守；假如执行环节出现无法继续按照方案推进的问题，参照 **拿不准的问用户** 规范，澄清事实后修改方案
    4. **修改后的事实不可变更**: docs/plan 目录下已经存在的历史提交文档不允许变更，过往事实记录禁止修改
    5. **更新施工状态**: 修改之后，将涉及模块的施工状态更新为 `施工中`, 并记录到 /docs/construction 中的文档里

- **施工方案格式规范**:
    1. 包含用户提出的需求理解
    2. 包含需求中的待澄清事项，没有就标明 `无待澄清事项`
    3. 针对确认后的最终需求，施工方案内容
    4. 针对方案内容是否有待澄清事项, 没有就标明 `无待澄清事项`, 并且锁定方案内容不再修改
    5. 施工方案的命名规范围遵守格式 `<日期>-<功能>-<涉及模块/架构层>-修改.md`

- **施工状态表说明**:
    1. 该状态表可能 **不会** 覆盖所有工程中存在的模块，没有在表中说明的视为 `空闲` 状态
    2. 模块的状态有两种: `空闲` 和 `施工中`, 被标记为 `施工中` 状态的模块不允许改动, `空闲` 的模块可以改动

- **编码规范**:
    1. **语言**: 代码注释、Commit Message、文档必须使用 **简体中文**。
    2. **类型安全**: 严禁使用 `any` (TS) 或隐式类型 (Python)。
    3. **错误处理**:
        - 后端必须使用 `HTTPException` 或自定义 `StatusCode` 处理错误。
        - 前端必须捕获 Axios 错误并统一处理 401/403 鉴权失效。
    4. **日志**: 后端统一使用 `loguru`，禁止直接使用 `print`。

- **验收标准**:
    1. **后端**: 检查后无 lint error
    2. **前端**: 能够顺利进行 npm run build 得到构建结果

