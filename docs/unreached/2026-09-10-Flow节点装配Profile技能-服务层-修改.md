# 2026-09-10 Flow 节点装配 Profile 技能 - 服务层 - 修改

## 用户需求理解

Flow 已去掉整图 Profile；`llm` 节点只绑定模型（`llm_ref`）。用户确认：**暂不**把 Profile 的 `skill_ids` 编进 Flow 的 `llm` 节点。Skill 装配仍只属于规划循环；Flow 工具继续走独立 `tool` 节点。

本文件仅登记未完事项。开工时移入 `docs/plan` 并按正式方案规范重写。

## 需求中的待澄清事项

开工前再确认：

1. `llm` 节点是装配 Skill 提示，还是隐式挂上规划工具环。
2. 是否改为节点绑 Profile 再取技能，还是另选 Skill 列表。

## 施工方案

未开工。预期方向：Flow `llm` 节点不隐式 ReAct；若做，应显式声明技能/工具，且与规划循环的 `SkillRuntime.assemble` 边界写清。

## 方案内容是否有待澄清事项

有，见第二节。未锁定。
