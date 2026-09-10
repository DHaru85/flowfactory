# 2026-08-21 Flow 去掉整图 Profile 绑定 - 映射层/服务层/应用层/表示层 - 修改

## 用户需求理解

当前 `agent_flow.profile_id` 为 **NOT NULL**：创建/保存 Flow 必须绑一个 Profile；Studio 顶栏与新建表单强制选同一个 Profile。这会让人以为整张图里所有 LLM 过程共用一套 Profile（模型、系统提示、技能），过程中无法按节点换更便宜或更强的模型。

事实：规划会话 / 规划 Beat 才以 Profile 为运行主体；Flow 编译已按节点读 `LlmNodeData.llm_ref`，**并不使用** `agent_flow.profile_id`。整图 FK 是误区。

原则：Flow 内每次 LLM 过程独立选模型；不在整图或节点上绑 Profile。规划侧（会话 `metadata.profile_id`、Beat `profile_id` 恰一）不变。

### 澄清过程

1. **Q1**：是否删除 `agent_flow.profile_id` 列？答：**删除**。
2. **Q2**：节点如何绑定？答：**下沉且只绑定模型**（`llm` 节点继续只写 `llm_ref`，不增加 `profile_ref`）。
3. **Q3**：是否把 Profile 的 `skill_ids` 编进 Flow `llm` 节点？答：**暂时不做**，写入 `docs/unreached`。

## 需求中的待澄清事项

无待澄清事项。

## 施工方案

> 方案已锁定。

### 1. 映射层

- 删除 `agent_flow.profile_id`；去掉 `AgentFlow.profile` / `AgentProfile.flows`。
- Alembic：drop FK + column。
- 硬删 Profile：去掉 `count_flows_for_profile` / `drop_deleted_flows_for_profile`。规划会话、Beat 引用检查不变。

### 2. 图定义与 Runtime

- `LlmNodeData` 保持 `llm_ref` 必填；不增加 Profile 字段。
- 编译仍按节点 `llm_ref` 解析客户端；`system_prompt` 仅为该节点提示，不再表述为「覆盖整图 Profile」。
- v0 图不引入 Profile。
- 设计文档：`agent_flow` 去掉 `profile_id`；Studio 创建/PATCH/详情去掉该字段。

### 3. 应用层 Studio

- 创建 Flow：body 仅 `name` + 可选 `definition`，不再收 `profile_id`。
- PATCH / 详情 / 列表：去掉 `profile_id`。
- `GET /studio/profiles` 保留（规划会话等目录仍可用）。

### 4. 表示层

- 新建 Flow 弹窗、画布顶栏：去掉整图 Profile 下拉。
- `llm` 节点 Inspector：只选 LLM（`llm_ref`）。
- Flow 传输类型去掉 `profile_id`。

### 5. 测试与验收

- 创建 Flow 不传 `profile_id`；响应无该字段。
- 集成里直接构造 `AgentFlow` 不再传 `profile_id`。
- ruff 无 error；相关 pytest 通过；`npm run build` 通过。

### 6. 明确不做

- 不改规划会话、规划 Beat、`PlannerRuntime`。
- 不把 Skill 装配进 Flow `llm` 节点（见 unreached）。
- 不升级 `schema_version`。

### 7. 施工状态

映射层 Agent、数据层 persistence、应用层 api、表示层 frontend 标为施工中；完成后空闲并写简报。

## 方案内容是否有待澄清事项

无待澄清事项。
