# InDepth 技能加载统一设计稿 V1

更新时间：2026-04-13
状态：V1 已实现（2026-04-13）

## 1. 背景与问题

当前代码中存在两套技能加载路径：
1. 轻量路径（legacy）：`app/core/skills/loader.py`
- 读取 `SKILL.md` 标题与首段摘要。
- 通过 `build_skill_prompt()` 一次性注入系统提示词。
- 主 Agent / Runtime 主要依赖该路径。

2. 管理器路径（new）：`app/core/skills/loaders.py` + `app/core/skills/manager.py`
- 支持结构化技能对象（name/description/instructions/scripts/references）。
- 支持按需技能访问工具（`get_skill_instructions/reference/script`）。
- 当前主要在 `SubAgent` 中使用。

并存问题：
1. 心智负担高：同名概念（SkillLoader）含义不同。
2. 行为不一致：主 Agent 只能看摘要，SubAgent 可按需读取完整内容。
3. 演进困难：新增能力要维护两条链路，测试与文档成本翻倍。

## 2. 目标

V1 统一目标：
1. 主 Agent / Runtime / SubAgent 统一走同一套“技能管理器”核心能力。
2. 保留“轻量注入”与“按需加载”两种消费方式，但底层数据源统一。
3. 兼容现有调用参数（`skills`、`skill_paths`），避免业务侧一次性改造。
4. 提供灰度开关与回滚路径，确保迁移风险可控。

## 3. 非目标

V1 不做：
1. 不改动技能目录规范（仍使用 `SKILL.md + scripts/ + references/`）。
2. 不引入远程技能仓库或联网分发。
3. 不变更工具权限模型（仅重构加载与注入流程）。

## 4. 统一后架构

统一原则：单一事实源（Single Source of Truth）
1. 统一读取层：`LocalSkills` 负责从路径读取并解析技能。
2. 统一管理层：`Skills` 负责缓存、查询、提示片段、访问工具暴露。
3. 统一消费层：
- Prompt 摘要注入：由 `Skills` 生成“摘要片段”。
- 按需访问：由 `Skills.get_tools()` 暴露访问工具。

建议接口（V1）：
1. 在 `Skills` 中新增 `get_summary_prompt_snippet()`：
- 输出与当前 `build_skill_prompt()` 近似的简版摘要，兼容主链路提示词长度控制。
2. `get_system_prompt_snippet()` 保留：
- 供具备技能工具的场景（如 SubAgent）使用。

## 5. 关键设计决策

1. 废弃策略
- `app/core/skills/loader.py` 标记为 deprecated。
- 在完成迁移后删除（或仅保留 thin wrapper 过渡一个版本）。

2. 构造方式统一
- 新增工厂函数（建议）：`build_skills_manager(skill_paths: list[str]) -> Skills`。
- 将字符串路径、数组路径统一归一化处理。

3. 注入策略统一
- 统一使用 `system` 模式：注入完整 `<skills_system>`。
- `runtime/main/sub` 三条链路行为一致。

4. 工具挂载统一
- 当且仅当加载到有效 skill 时，统一挂载技能访问工具：
- `get_skill_instructions`
- `get_skill_reference`
- `get_skill_script`

## 6. 迁移方案（分阶段）

Phase 1：能力对齐（无行为变更）
1. 在 `Skills` 中补齐 summary 片段接口。
2. 增加 `build_skills_manager` 工厂。
3. 保持现有主链路仍可运行，输出与旧版近似。

Phase 2：主链路切换
1. `app/agent/agent.py` 与 `app/core/bootstrap.py` 改为使用 `Skills`。
2. 移除对 legacy `SkillLoader` 的直接依赖。
3. 与 `SubAgent` 对齐，统一为 system prompt + skill tools。

Phase 3：收口与清理
1. 删除或冻结 `app/core/skills/loader.py`。
2. 统一文档与测试基线。
3. 清理重复命名，避免 `SkillLoader` 概念歧义。

## 7. 兼容与回滚（当前实现）

兼容策略：
1. 输入兼容：继续接受 `skills: str | list[str] | None`。
2. 输出策略：统一输出 `<skills_system>` 片段（不再保留 summary 作为主链路）。
3. 工具兼容：仅在存在有效 skills 时挂载技能访问工具。

回滚策略：
1. 当前版本已移除 legacy 回退开关与 legacy loader。
2. 若需回滚，只能通过代码回滚（git revert）。

## 8. 测试要求

最小回归集：
1. `test_unified_loader_accepts_string_and_list_paths`
2. `test_summary_prompt_equivalent_to_legacy_style`
3. `test_system_prompt_contains_available_skills_and_tools`
4. `test_agent_uses_skills_manager_in_system_mode`
5. `test_subagent_uses_skills_manager_in_system_mode`
6. `test_invalid_skill_path_fails_deterministically`
7. `test_feature_flag_can_fallback_to_legacy`

## 9. 风险与应对

1. Token 增加风险
- 应对：当前统一 system 模式；后续若出现成本压力，再在 V2 引入可配置 prompt 等级。

2. 运行行为变化风险（工具调用路径变化）
- 应对：主链路默认不挂技能工具，仅替换底层加载来源。

3. 技能解析严格校验导致历史技能加载失败
- 应对：提供 `validate` 开关；迁移期默认宽松校验并记录告警。

## 10. 实施清单

1. 新增 `Skills` summary 接口与 manager 工厂。
2. 主 Agent / Bootstrap 切换到统一 manager。
3. 统一 runtime/main/sub 的 system prompt 与 skill tools 挂载行为。
4. 补测试并更新 `doc/refer/architecture-reference.md` 与技能说明文档。

## 11. 验收标准

1. 代码中仅保留一套有效技能加载主链路。
2. 主 Agent、Runtime、SubAgent 均基于统一 manager 构建技能上下文，且接入行为一致（system + tools）。
3. 回归测试通过，且关键场景行为与迁移前一致或可解释。
