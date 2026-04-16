# InDepth Skills 参考

更新时间：2026-04-16

## 1. 定位

`app/core/skills/*` 提供统一的技能加载与访问机制，用于：
1. 在系统提示词注入 `<skills_system>`（列出可用技能）。
2. 向模型暴露技能访问工具（按需读取 instructions/references/scripts）。

当前已统一：`BaseAgent`、`create_runtime`、`SubAgent` 都基于 `Skills manager` 接入。

## 2. 核心模块

1. `app/core/skills/factory.py`
- `build_skills_manager(skill_paths, validate=False)`：统一构建入口。
- 兼容输入：技能目录、`SKILL.md` 路径、技能集合目录（如 `app/skills`）。

2. `app/core/skills/loaders.py`
- `LocalSkills`：从本地路径读取技能，解析 frontmatter 与正文。
- 自动发现：
  - `scripts/` 下脚本文件名
  - `references/` 下参考文件名

3. `app/core/skills/manager.py`
- `Skills`：缓存技能对象、生成 prompt 片段、暴露技能访问工具。
- `get_system_prompt_snippet()`：输出 `<skills_system>`。
- `get_tools()`：返回三个工具：
  - `get_skill_instructions(skill_name)`
  - `get_skill_reference(skill_name, reference_path)`
  - `get_skill_script(skill_name, script_path, execute=False, args=[], timeout=30)`

4. `app/core/skills/skill.py`
- `Skill` 数据结构：`name/description/instructions/source_path/scripts/references/...`

## 3. 接入链路

```
skill_paths
   │
   ▼
build_skills_manager(...)
   │
   ▼
LocalSkills.load()
   │
   ▼
Skills(_skills)
   ├── get_system_prompt_snippet() ──▶ 注入 runtime.skill_prompt
   └── get_tools() ──────────────────▶ 注册到 ToolRegistry
```

## 4. 运行时行为

1. 启动阶段
- 根据 `skill_paths` 构建 `Skills manager`。
- 将 `<skills_system>` 注入 system prompt。
- 若技能列表非空，注册技能访问工具。

2. 推理阶段
- 模型先看到 `<skills_system>` 中的技能目录。
- 需要具体内容时，再调用技能工具按需加载。
- `SKILL.md` 正文、`references`、`scripts` 不会在启动时全量注入。

3. 上下文保留
- 技能工具返回会作为 `tool` 消息进入会话记忆。
- 后续轮次可能被上下文压缩，通常保留摘要而非完整原文。

## 5. 各 Agent 默认配置

1. `BaseAgent`（`app/agent/agent.py`）
- 技能来源：构造参数 `skills`（`str/list/None`）。
- 有技能时注入 `<skills_system>` 并挂载技能工具。

2. `Runtime CLI`（`app/agent/runtime_agent.py`）
- 默认 `skill_paths=["app/skills"]`，即加载项目内全部技能。
- 运行在单一 `task` 模式；普通输入统一走执行链路。

3. `SubAgent`（`app/agent/sub_agent.py`）
- 默认 `skill_paths=["app/skills/memory-knowledge-skill"]`。
- 同样注入 `<skills_system>` 并挂载技能工具。

4. `VerifierAgent`（`app/eval/agent/verifier_agent.py`）
- 不走 skills 模块（独立评估工具链）。

## 6. 技能目录规范

每个技能目录最少包含：
1. `SKILL.md`

可选目录：
1. `scripts/`
2. `references/`

`SKILL.md` 推荐包含 frontmatter：
1. `name`
2. `description`

## 7. 常见问题

1. 为什么 `get_system_prompt_snippet()` 为空？
- 传入的 `skill_paths` 为空，或路径不存在，或目录下没有可识别的 `SKILL.md`。

2. 调用一次 `get_skill_instructions` 后会一直保留全文吗？
- 不保证。短期在消息中可见，长期可能被压缩为摘要。

3. 可以一次加载整个 `app/skills` 吗？
- 可以。`build_skills_manager(["app/skills"], validate=False)` 会扫描其下技能子目录。
