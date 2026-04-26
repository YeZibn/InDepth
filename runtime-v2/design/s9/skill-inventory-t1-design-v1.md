# S9-T1 当前 Skill 链路清单（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T1`

## 1. 目标

本任务用于盘点当前项目中的 skill 链路现状，并给出可参考的外部框架抽象，作为后续 `S9-T2 ~ S9-T6` 的输入。

本任务只回答三件事：

1. 当前 skill 在项目里由哪些部分组成
2. 当前 skill 如何影响 prompt、tool 和 runtime
3. 市面上类似框架有哪些可借鉴抽象

## 2. 正式结论

当前项目中的 skill 链路，至少由以下 4 个部分组成：

1. `skill asset`
2. `skill loading`
3. `skill prompt exposure`
4. `skill tool exposure`

并且当前 skill 的主要现状类型，不是单一 prompt 片段，而是：

1. prompt capability
2. prompt + tool capability

## 3. 当前 Skill 链路总览

| 组成部分 | 当前落点 | 作用 | 对 v2 的意义 |
|---|---|---|---|
| `skill asset` | `app/skills/*` | 保存 `SKILL.md`、references、scripts 等资源 | 是 skill 的静态能力包本体 |
| `skill loading` | `app/core/skills/loaders.py`, `factory.py`, `manager.py` | 负责加载、解析、管理 skill | 是 skill 进入 runtime 的入口 |
| `skill prompt exposure` | `Skills.get_system_prompt_snippet()`, `get_summary_prompt_snippet()` | 把 skill 说明暴露给模型 | 对接 `S1` 的 `capability layer` |
| `skill tool exposure` | `Skills.get_tools()` 与 `get_skill_*` 工具 | 让 skill 资源通过工具访问 | 对接 `S6` 的正式 tool 系统 |

## 4. 当前 Skill 资产

当前本地可见 skill 资产至少包括：

| skill_name | source_path | 主要资源 | 当前形态判断 |
|---|---|---|---|
| `memory-knowledge-skill` | `app/skills/memory-knowledge-skill` | `SKILL.md`、references、scripts | `prompt + tool` 型 |
| `ppt-skill` | `app/skills/ppt-skill` | `SKILL.md`、references | `prompt-centric` 型 |
| `skill-creator` | `app/skills/skill-creator` | `SKILL.md`、scripts | `prompt + tool/script` 型 |

## 5. 当前 Loading 链路

当前 skill loading 链路主要如下：

| 环节 | 当前代码位置 | 作用 |
|---|---|---|
| 路径输入 | `BaseAgent.skills` / `skill_paths` | 指定 skill 路径来源 |
| 工厂构建 | `app/core/skills/factory.py` | 构建 `Skills` manager |
| 本地加载 | `app/core/skills/loaders.py` | 从目录或 `SKILL.md` 解析 skill |
| 运行时管理 | `app/core/skills/manager.py` | 统一提供 prompt snippet、tool exposure、skill 查询 |

当前链路特点：

1. skill 是以目录为中心加载的
2. `SKILL.md` 是正式入口
3. references / scripts 是附属资源

## 6. 当前 Prompt 暴露链路

当前 skill 对 prompt 的暴露主要有两种方式：

| 暴露方式 | 当前接口 | 作用 |
|---|---|---|
| system snippet | `get_system_prompt_snippet()` | 提供完整技能访问说明与资源入口 |
| summary snippet | `get_summary_prompt_snippet()` | 提供轻量 skill 摘要 |

当前判断：

1. 这两种暴露方式都属于 `S1` prompt assembly 范围
2. 在 v2 中应统一收敛到 `capability layer`

## 7. 当前 Tool 暴露链路

当前 skill 还能通过工具暴露自己的资源访问能力。

主要接口如下：

| tool_name | 当前作用 | 说明 |
|---|---|---|
| `get_skill_instructions` | 读取 skill 完整说明 | 适合按需加载 instructions |
| `get_skill_reference` | 读取 skill reference 文件 | 适合按需读取参考资料 |
| `get_skill_script` | 读取或执行 skill script | 适合按需调用 skill 附带脚本 |

当前判断：

1. skill 自身可以提供 tool，这一点没有问题
2. 这些 tool 在 v2 中仍应归统一 tool 系统治理
3. skill 负责描述和打包，tool 负责正式能力暴露

## 8. 当前 Skill 对 Runtime 的作用位置

结合当前实现，skill 现状主要影响以下位置：

| 作用位置 | 当前体现 | v2 对应落点 |
|---|---|---|
| prompt 注入 | `skill_prompt` 拼到系统 prompt | `capability layer` |
| tool 注册 | `skills_manager.get_tools()` 注册到 registry | `S6` tool system |
| 资源访问 | references / scripts 按需读取 | `S9` skill 资源模型 |

## 9. 外部参考框架

本任务参考了两类公开框架：

| 框架 | 公开特征 | 可借鉴点 |
|---|---|---|
| Codex | Skills 强调“instructions + resources + scripts”的能力包，并可连接工具与工作流 | 适合作为 `skill = 能力包` 的参考抽象 |
| Claude Code | 由 `CLAUDE.md`、slash commands、subagents、MCP、hooks 共同构成能力层 | 适合作为“能力拆层而非单一 skill 子系统”的参考 |

参考来源：

1. [OpenAI Codex](https://openai.com/codex)
2. [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)
3. [Claude Code slash commands](https://docs.anthropic.com/en/docs/claude-code/slash-commands)
4. [Claude Code subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
5. [Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp)
6. [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)

## 10. 外部参考后的抽象结论

结合外部参考，本任务建议把 skill 先理解成：

1. 能力说明包
2. 资源打包单元
3. 可选 tool 暴露单元

而不是仅仅理解为：

1. prompt 片段

同时，本任务明确区分：

1. `skill` 可以提供 tool
2. 但 tool 仍应归统一 tool 系统治理

## 11. 对后续任务的直接输入

`S9-T1` 直接服务：

1. `S9-T2` skill 正式角色定义
2. `S9-T3` skill manifest
3. `S9-T4` skill 与 prompt/tool/resource/dependency 的关系
4. `S1` capability layer 的后续细化

## 12. 本任务结论摘要

可以压缩成 6 句话：

1. 当前 skill 链路至少由 asset、loading、prompt exposure、tool exposure 四部分组成
2. 当前 skill 不是单一 prompt 片段，而是能力包
3. skill 现状既有 prompt-only，也有 prompt + tool 类型
4. 当前 skill prompt 在 v2 中应进入 `capability layer`
5. skill 自身可以提供 tool，但 tool 仍归统一 tool 系统治理
6. Codex 和 Claude Code 都说明能力层应当是“说明、资源、工具、协作”的组合结构
