# S1-T1 Prompt 资产清单（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S1-T1`

## 1. 目的

本文用于盘点当前项目中实际参与运行的 prompt 资产，覆盖：

1. 主 Agent system prompt
2. phase prompt
3. subagent role prompt
4. verification prompt
5. 判断类 prompt
6. 记忆与偏好注入 prompt
7. skill prompt 注入

本文重点回答三件事：

1. prompt 资产现在分布在哪里
2. 它们如何进入模型上下文
3. 它们当前承担什么职责

## 2. 总览

当前 prompt 资产可以分为 7 类：

1. 基础 system prompt
2. phase overlay prompt
3. prepare planner prompt
4. subagent role prompt
5. verifier / judge prompt
6. dynamic injection prompt
7. skill prompt

## 3. Prompt 资产总表

| 资产编号 | 类别 | 资产名称 | 来源 | 进入位置 | 动态/静态 | 当前作用 |
|---|---|---|---|---|---|---|
| P-001 | 基础 system prompt | InDepth 协议文本 | `InDepth.md` | BaseAgent -> AgentRuntime.system_prompt | 静态 | 定义主 Agent 的总体行为协议 |
| P-002 | 基础 system prompt | Agent instructions | `app/agent/agent.py` 构造参数 `instructions` | BaseAgent -> AgentRuntime.system_prompt | 半静态 | 追加具体 Agent 指令 |
| P-003 | skill prompt | Skills system snippet | `app/core/skills/manager.py` | `AgentRuntime.skill_prompt` | 动态 | 向主 Agent 暴露 skill 元数据与访问方式 |
| P-004 | phase prompt | Prepare phase prompt | `app/core/runtime/agent_runtime.py` `PREPARING_PHASE_PROMPT` | `_build_system_prompt()` | 静态 | 约束准备阶段行为与输出 |
| P-005 | phase prompt | Execute phase prompt | `app/core/runtime/agent_runtime.py` `EXECUTING_PHASE_PROMPT` | `_build_system_prompt()` | 静态 | 约束执行阶段行为 |
| P-006 | phase prompt | Finalize phase prompt | `app/core/runtime/agent_runtime.py` `FINALIZING_PHASE_PROMPT` | `_build_system_prompt()` | 静态 | 约束收尾阶段输出格式与真实性 |
| P-007 | planner prompt | Prepare planner prompt | `PREPARING_PHASE_PROMPT` 复用 | `_run_prepare_phase_llm()` | 静态 + 动态输入 | 驱动 prepare 规划器输出结构化结果 |
| P-008 | dynamic injection | Prepare phase message | `AgentRuntime._render_prepare_phase_message()` | `messages.append({"role":"system"})` | 动态 | 把 prepare 产物再次注入主执行上下文 |
| P-009 | dynamic injection | System memory recall block | `app/core/runtime/system_memory_lifecycle.py` | 注入 `messages[0]` 后或前置 system message | 动态 | 注入经验召回结果 |
| P-010 | dynamic injection | User preference recall block | `app/core/runtime/user_preference_lifecycle.py` | 在首个 user message 前插入 system message | 动态 | 注入用户偏好摘要 |
| P-011 | verifier prompt | Verifier agent system prompt | `app/eval/agent/verifier_agent.py` | VerifierAgent 调用模型时 | 静态 | 独立评估代理的 system prompt |
| P-012 | judge prompt | Clarification judge system prompt | `app/core/runtime/clarification_policy.py` | 澄清判定模型调用 | 静态 | 判定 assistant 输出是否为澄清请求 |
| P-013 | judge prompt | Clarification judge user prompt template | `app/core/runtime/clarification_policy.py` | 澄清判定模型调用 | 动态模板 | 传入 user_input / assistant_output 做判断 |
| P-014 | judge prompt | User preference extract system prompt | `app/core/runtime/user_preference_lifecycle.py` | 偏好抽取模型调用 | 静态 | 约束偏好抽取器只输出 JSON |
| P-015 | judge prompt | User preference extract user template | `app/core/runtime/user_preference_lifecycle.py` | 偏好抽取模型调用 | 动态模板 | 传入用户输入以抽取偏好 |
| P-016 | subagent role prompt | general | `app/agent/prompts/sub_agent_roles/general.md` | subagent 初始化时 | 动态模板 | 通用子代理角色约束 |
| P-017 | subagent role prompt | builder | `app/agent/prompts/sub_agent_roles/builder.md` | subagent 初始化时 | 动态模板 | 实现型子代理角色约束 |
| P-018 | subagent role prompt | researcher | `app/agent/prompts/sub_agent_roles/researcher.md` | subagent 初始化时 | 动态模板 | 检索型子代理角色约束 |
| P-019 | subagent role prompt | reviewer | `app/agent/prompts/sub_agent_roles/reviewer.md` | subagent 初始化时 | 动态模板 | 审查型子代理角色约束 |
| P-020 | subagent role prompt | verifier | `app/agent/prompts/sub_agent_roles/verifier.md` | subagent 初始化时 | 动态模板 | 验证型子代理角色约束 |

## 4. 分类盘点

## 4.1 基础 system prompt

### P-001 InDepth 协议文本

来源：

- `InDepth.md`
- 通过 [agent.py](/Users/yezibin/Project/InDepth/app/agent/agent.py) 中 `load_indepth_content()` 读取

挂载方式：

1. `BaseAgent` 在初始化时将 `InDepth.md` 内容与 `instructions` 拼接。
2. 拼接结果作为 `system_prompt` 传给 `AgentRuntime`。

当前作用：

1. 提供主 Agent 的最高层行为协议。
2. 约束任务完成、验证、工具使用等总体原则。

问题特征：

1. 它同时承担“产品协议”和“运行约束”两类职责。
2. 当前是大块静态文本，未做分层。

### P-002 Agent instructions

来源：

- `BaseAgent(..., instructions=...)`

挂载方式：

1. 与 `InDepth.md` 拼接后进入 `AgentRuntime.system_prompt`。

当前作用：

1. 为不同宿主 Agent 补充个性化说明。

问题特征：

1. 目前和 `InDepth.md` 是直接拼接关系，未区分“框架协议”和“实例说明”。

## 4.2 Skill prompt

### P-003 Skills system snippet

来源：

- [manager.py](/Users/yezibin/Project/InDepth/app/core/skills/manager.py) `get_system_prompt_snippet()`

挂载方式：

1. `build_agent_runtime_kwargs()` 调用 skills manager 生成 `skill_prompt`
2. `AgentRuntime._build_system_prompt()` 将 `self.system_prompt` 与 `self.skill_prompt` 拼接

当前作用：

1. 把 skill 名称、描述、references、scripts 暴露给主 Agent
2. 指示主 Agent 通过 skill access tools 按需读取技能内容

问题特征：

1. 这是元数据 prompt，不是技能正文 prompt。
2. 当前直接并入 system prompt 主体，后续可能需要独立层。

## 4.3 Phase prompt

### P-004 Prepare phase prompt

来源：

- [agent_runtime.py](/Users/yezibin/Project/InDepth/app/core/runtime/agent_runtime.py) `PREPARING_PHASE_PROMPT`

挂载方式：

1. `AgentRuntime._runtime_phase == "preparing"` 时
2. `PHASE_OVERLAY_PROMPTS` 参与 `_build_system_prompt()`

当前作用：

1. 约束 prepare 阶段只做执行入口建立
2. 定义 todo 决策要求
3. 定义 subagent 编排要求
4. 约束 prepare planner 的结构化输出

问题特征：

1. 既是 phase prompt，又兼任 prepare planner prompt。
2. 同时承载运行时阶段约束和 planner 输出 schema，职责偏重。

### P-005 Execute phase prompt

来源：

- `EXECUTING_PHASE_PROMPT`

挂载方式：

1. 进入 executing 阶段后由 `_build_system_prompt()` 注入

当前作用：

1. 约束执行阶段不要偏离计划
2. 约束 subagent 只能按 prepare 决策执行

问题特征：

1. 主要是行为约束 prompt，结构相对纯粹。

### P-006 Finalize phase prompt

来源：

- `FINALIZING_PHASE_PROMPT`

挂载方式：

1. 进入 finalizing 阶段后由 `_build_system_prompt()` 注入

当前作用：

1. 强制模型输出 `[Final Answer]` 与 `[Structured Handoff]`
2. 提供 handoff JSON schema
3. 定义 final_status、known_gaps、memory_seed 等字段规则

问题特征：

1. 当前是最强协议化 prompt 之一。
2. 已经非常接近正式接口定义。

## 4.4 Prepare planner prompt

### P-007 Prepare planner prompt

来源：

- prepare 阶段 LLM 规划直接复用 `PREPARING_PHASE_PROMPT`

挂载方式：

1. `_run_prepare_phase_llm()` 中直接以：
   - `system = PREPARING_PHASE_PROMPT`
   - `user = json.dumps(payload)`
   调用模型

当前作用：

1. 让 prepare planner 产出 JSON 计划结果
2. 作为 `plan_task` 的前置规划器

问题特征：

1. 运行阶段 prompt 与 planner prompt 目前未拆开。
2. 后续 v2 可能需要把“phase prompt”和“planner contract”分离。

## 4.5 Dynamic injection prompt

### P-008 Prepare phase message

来源：

- `AgentRuntime._render_prepare_phase_message()`

挂载方式：

1. prepare 完成后，将 prepare 结果拼成一段新的 system message 插入主消息链

当前作用：

1. 把 prepare 结论回灌给执行阶段模型
2. 提醒后续优先沿用 prepare 的 plan 和 suggested args

问题特征：

1. 这是典型的“状态通过消息回灌”。
2. 属于 v2 需要重点收敛的隐式状态编码点。

### P-009 System memory recall block

来源：

- `render_memory_recall_block(...)`
- [system_memory_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/system_memory_lifecycle.py)

挂载方式：

1. 在 run 开始时召回 system memory
2. 将 recall block 注入消息链，通常作为 system message 前置

当前作用：

1. 提供历史经验卡的上下文补充

问题特征：

1. 它是 runtime 生命周期触发，但以 prompt 片段形式注入。
2. 当前 recall 策略与注入协议没有完全解耦。

### P-010 User preference recall block

来源：

- `UserPreferenceStore.render_recall_block(...)`
- [user_preference_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/user_preference_lifecycle.py)

挂载方式：

1. run 开始时在首个 user message 前插入 system message

当前作用：

1. 提供用户长期偏好信息

问题特征：

1. 注入位置和 system memory recall block 不完全一致。
2. 说明当前 dynamic injection 尚未标准化。

## 4.6 Judge / extractor prompt

### P-011 Verifier agent system prompt

来源：

- [verifier_agent.py](/Users/yezibin/Project/InDepth/app/eval/agent/verifier_agent.py) `VERIFIER_AGENT_SYSTEM_PROMPT`

挂载方式：

1. 仅在独立 VerifierAgent 内部使用

当前作用：

1. 约束 verifier 按 JSON 输出评估结果
2. 指导 verifier 根据证据根目录与 handoff 做判断

### P-012 / P-013 Clarification judge prompts

来源：

- [clarification_policy.py](/Users/yezibin/Project/InDepth/app/core/runtime/clarification_policy.py)

组成：

1. `CLARIFICATION_JUDGE_SYSTEM_PROMPT`
2. `CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE`

挂载方式：

1. 在 stop 分支中，作为单独的判定模型调用使用

当前作用：

1. 判断 assistant 输出是否属于澄清请求

### P-014 / P-015 User preference extract prompts

来源：

- [user_preference_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/user_preference_lifecycle.py)

组成：

1. `USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT`
2. `USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE`

挂载方式：

1. 在任务结束后或 capture 时，调用单独模型进行偏好抽取

当前作用：

1. 约束偏好抽取器从用户输入中提取结构化更新

问题特征：

1. 这是 prompt 资产，但不进入主 Agent 执行上下文。
2. 属于“辅助判定/抽取型 prompt”。

## 4.7 SubAgent role prompts

来源：

- [general.md](/Users/yezibin/Project/InDepth/app/agent/prompts/sub_agent_roles/general.md)
- [builder.md](/Users/yezibin/Project/InDepth/app/agent/prompts/sub_agent_roles/builder.md)
- [researcher.md](/Users/yezibin/Project/InDepth/app/agent/prompts/sub_agent_roles/researcher.md)
- [reviewer.md](/Users/yezibin/Project/InDepth/app/agent/prompts/sub_agent_roles/reviewer.md)
- [verifier.md](/Users/yezibin/Project/InDepth/app/agent/prompts/sub_agent_roles/verifier.md)

挂载方式：

1. subagent 创建时，根据 role 选择对应模板
2. 模板中插入 `{role}`、`{task}`、`{extra_instructions}`

当前作用：

1. 约束不同角色子代理的职责边界
2. 统一子代理输出结构

问题特征：

1. role prompt 已经独立文件化，是当前最清晰的一类 prompt 资产。
2. 但角色模板与主 runtime 的 phase 约束仍未统一建模。

## 5. 当前挂载路径

当前主 Agent 的 system prompt 组装链路如下：

```text
InDepth.md
  + Agent instructions
  -> system_prompt

skills_manager.get_system_prompt_snippet()
  -> skill_prompt

AgentRuntime._build_system_prompt()
  = system_prompt + skill_prompt + phase_prompt
```

随后在一次 run 中，还会继续注入动态 prompt：

```text
run start
  -> inject_user_preference_recall()
  -> inject_system_memory_recall()
  -> prepare phase
  -> render_prepare_phase_message()
  -> executing / finalizing
```

此外，还有两类不进入主执行上下文的 prompt：

1. judge / extractor prompt
2. verifier / subagent prompt

## 6. 当前问题总结

从 prompt 资产角度看，当前实现有 5 个主要问题：

1. 基础协议 prompt、phase prompt、planner prompt、dynamic injection prompt 尚未分层。
2. prepare phase prompt 兼任了 phase 约束和 planner contract 两种角色。
3. 多种动态注入 prompt 的插入位置不统一。
4. 一部分运行状态仍通过 system message 隐式编码。
5. 主 Agent、Verifier、SubAgent、Judge/Extractor 几类 prompt 体系尚未统一到一套总模型下。

## 7. 对 S1-T2 的直接输入

这份资产清单会直接为后续 `S1-T2` 提供输入，重点包括：

1. 明确哪些属于 base prompt。
2. 明确哪些属于 phase overlay。
3. 明确哪些属于 dynamic injection。
4. 明确哪些属于 auxiliary prompt。
5. 明确哪些 prompt 当前承担了超出自身层级的职责。

