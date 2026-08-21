# 2026-08-21 Agent 族 code 服务层生成 - 表示层应用层服务层 - 修改

## 用户需求理解

Agent 族（LLM / Profile / Skill / Tool / MCP / Flow / Beat）的 `code` 只作图拓扑与运行时解析指针。表示层不得出现 code 的输入、列、下拉文案；创建由服务层生成 `{kind}-{8位hex}`；落库后只读。角色/组织/知识库/护栏不在本轮。

## 需求中的待澄清事项

无待澄清事项

## 施工方案

1. `service.agent_code.generate_agent_code`；仓储 `allocate_code` 查重后分配。创建体去掉 `code`；PATCH 本就无该字段（多余字段忽略）。
2. Studio 已发布目录补充 `name`，画布/子图选择展示名称；`llm_ref`/`tool_code`/`flow_code` 仍写入 definition，界面用 name。
3. 表示层：配置/模型/Studio 列表与表单去掉 code；会话与目录下拉用 name；面包屑用 `name`+version。
4. 单测改为不传 code、断言生成前缀。pytest、ruff、`npm run build`。

## 方案待澄清事项

无待澄清事项
