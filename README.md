# InDepth

InDepth 是一个面向本地执行场景的 Agent Runtime，强调三件事：
- 可执行：把对话转成可控执行流程（tool-calling + runtime loop）
- 可观测：全链路事件、时间线、复盘报告
- 可验证：区分"回答完成"和"任务完成"

## 1. 背景与动机

### 1.1 问题

LLM 对话界面天然适合"问-答"模式，但在实际工作中，我们需要的往往不是一段回答，而是**一个可交付的结果**：

| 对话模式 | 实际需求 |
|---------|---------|
| "帮我写一段代码" | 写完、跑通、通过 code review |
| "帮我分析竞品" | 输出结构化报告、附上数据来源 |
| "帮我做这个功能" | 代码改好、测试通过、可合并 |

问题在于：对话系统无法区分"回答像完成了"和"任务真完成了"。

### 1.2 解决思路

InDepth 的核心命题：**把"任务完成"变成一个可验证、可复盘、可积累的工程过程**。

- **可执行**：不只给答案，要让 AI 能真正调用工具、修改文件、执行命令
- **可验证**：不只靠"看起来对"，要有硬判定（stop reason、tool failure）和软判定（LLM judge）
- **可观测**：不只记录最终输出，要记录完整执行路径（事件流、时间线）
- **可积累**：不只一次性的对话，要在多次运行中沉淀经验（memory card）

### 1.3 核心区别

| 维度 | 对话式 AI | InDepth |
|------|----------|---------|
| 执行能力 | 文本生成 | tool-calling + 真实环境操作 |
| 结果验证 | 主观判断 | deterministic verifier + LLM judge |
| 执行追踪 | 无 | 全链路事件 + 时间线 |
| 经验复用 | 无 | system memory + 经验卡 |

## 2. 设计哲学

InDepth 的设计遵循以下原则：

### 2.1 协议先行（Protocol First）

**定义边界比执行更重要**。在开始干活之前，先把"什么算成功"写清楚。

- `InDepth.md` 是任务的宪法，所有参与者（Runtime、Agent、工具层）都必须遵循
- 验收标准必须是明确的、可判定的，而不是模糊的"看起来不错"

### 2.2 验证与执行分离（Separation of Execution and Judgement）

**做的人和判断的人要分开**。

- 执行层（Runtime + Tools）负责把事情做出来
- 验证层（EvalOrchestrator）负责判断是否真完成了
- 两者独立运作，互不干扰

### 2.3 可审计（Auditability）

**每一个决定都要有迹可循**。

- 所有关键事件（agent started、tool called、task finished）都写入事件流
- 每次判定都有 breakdown，说明为什么 pass/partial/fail
- 每次运行都生成 postmortem，记录学到了什么

### 2.4 经验可积累（Learning from Experience）

**不要每次都从零开始**。

- Runtime memory 压缩历史，避免上下文爆炸
- System memory 沉淀经验卡，供后续任务检索
- 记忆事件（triggered/retrieved/decision）进入观测链路

### 2.5 子代理角色化（Role-based SubAgent）

**专业的人做专业的事**。

- `researcher`：调研、检索、资料收集
- `builder`：开发、代码实现、修复
- `reviewer`：审查、风险评估、回归检查
- `verifier`：验证、测试、lint/typecheck
- `general`：默认角色

## 3. 核心能力

- Runtime 编排：多轮推理、工具调用、收敛控制
- Runtime 澄清恢复：`awaiting_user_input` 挂起 + 同一 `run_id` 恢复执行
- Tool 体系：统一声明、注册、参数校验、调用封装
- SubAgent 协同：角色化子代理与并行执行
- Skills 统一接入：`build_skills_manager` + `<skills_system>` + 技能访问工具（按需读取 instructions/references/scripts）
- Todo 编排：统一 `todo_id` 语义，避免与 Runtime `task_id` 混淆
- Eval 判定：deterministic verifier + 可选 LLM judge
- Observability：事件落盘、指标聚合、postmortem
- Memory 闭环：运行时压缩摘要 + 系统经验卡沉淀

## 4. 快速开始

### 4.1 安装与运行

1. 安装依赖
   - `pip install -r requirements.txt`
2. 配置模型环境变量
   - `LLM_MODEL_ID`
   - `LLM_MODEL_MINI_ID`
   - `LLM_API_KEY`
   - `LLM_BASE_URL`
3. 启动 CLI
   - `python app/agent/runtime_agent.py`
   - 默认加载 `app/skills/` 下全部技能（当前为 `memory-knowledge-skill`、`ppt-skill`、`skill-creator`）

### 4.2 关键目录

```text
app/
  agent/                 # BaseAgent、SubAgent、CLI 入口
  core/
    runtime/             # AgentRuntime 主循环
    model/               # 模型适配层
    tools/               # 工具协议/注册/校验
    memory/              # 记忆存储与压缩
    skills/              # 技能加载与管理
  tool/                  # 具体工具实现
  eval/                  # 任务评估体系
  observability/         # 观测、指标、复盘
db/                      # runtime/system memory sqlite
todo/                    # 任务拆解文件
work/                    # 交付物输出
observability-evals/     # 评估与复盘输出
InDepth.md               # 运行协议
```

## 5. 分层架构

InDepth 的执行过程可以理解为一条连续的生产线：先定义边界，再推进执行；先完成结果，再验证结果；最后把过程沉淀为可复用经验。

1. 协议层（L1）
   - 作用：在执行前定义“什么是成功”，避免后续流程方向漂移。
   - 关键模块：`InDepth.md`。
   - 主要内容：
     - 任务目标与范围边界
     - 时效性信息门禁（时间基准、检索预算、停止阈值）
     - 子任务拆解与 SubAgent 协同规则
     - 结果验收口径与风险约束
   - 输出：一组可执行的规则约束，供 Runtime 与工具层遵循。

2. 编排层（L2）
   - 作用：把用户输入转换为稳定的“推理-执行-收敛”循环。
   - 关键模块：`app/core/runtime/agent_runtime.py`。
   - 主要流程：
     - 组装消息上下文（system + history + user）
     - 调模型并解析 `finish_reason`
     - 命中澄清意图时进入 `awaiting_user_input`，等待用户补充后在同一 run 恢复
     - 执行 tool-calling 分支并回写工具结果
     - 处理 stop/length/content_filter 等收敛分支
     - 在运行中触发上下文压缩，在结束时执行最终压缩
   - 输出：`final_answer`、`stop_reason`、运行状态，以及后续评估所需执行证据。

3. 能力层（L3）
   - 作用：把抽象计划落成具体动作（命令、文件、检索、任务编排）。
   - 关键模块：
     - 工具框架：`app/core/tools/*`
     - 工具实现：`app/tool/*`
     - 子代理体系：`app/agent/sub_agent.py` + `app/tool/sub_agent_tool/*`
   - 主要能力：
     - 基础执行：bash、读写文件、时间工具
     - 检索执行：search guard 门禁下的受控搜索
     - 任务编排：todo 工具（创建子任务、状态流转、依赖约束，参数统一为 `todo_id`）
     - 并行协同：SubAgent 角色化执行（researcher/builder/reviewer/verifier）
   - 输出：结构化工具结果、子任务状态变化、可追溯执行日志。

4. 验证层（L4）
   - 作用：把“回答像完成”与“任务真完成”分离。
   - 关键模块：`app/eval/*`（`EvalOrchestrator`、`verifiers`、`VerifierAgent`）。
   - 判定机制：
     - 硬判定：`StopReasonVerifier`、`ToolFailureVerifier`
     - 软判定：可选 LLM Judge（评分与理由）
     - 最终输出：`pass / partial / fail` + `overclaim` + breakdown
   - 输出：`task_judged` 判定结果（系统级最终判定依据）。

5. 记忆层（L5）
   - 作用：让系统具备“经验可积累、后续可复用”的长期能力。
   - 关键模块：
     - Runtime memory：`app/core/memory/sqlite_memory_store.py`
     - 压缩器：`app/core/memory/context_compressor.py`
     - System memory：`app/core/memory/system_memory_store.py`
   - 主要机制：
     - 运行中压缩历史消息为 `summary_json`（保留关键约束/决策/产物锚点）
     - 任务结束强制沉淀经验卡（`memory_card`）
     - 记忆事件（triggered/retrieved/decision）进入 observability 链路
   - 输出：结构化历史摘要、系统经验卡、可统计的记忆治理数据。

### 5.1 System Architecture

![InDepth System Architecture](doc/assets/readme/architecture-paper-style.svg)

## 6. 参考文档

详细实现说明在 `doc/refer/`：

| 文档 | 说明 |
|------|------|
| [总索引](doc/refer/README.md) | 文档索引与阅读顺序 |
| [Runtime](doc/refer/runtime-reference.md) | AgentRuntime 主循环、收敛逻辑 |
| [Skills](doc/refer/skills-reference.md) | 技能加载、`<skills_system>` 注入、技能访问工具 |
| [Memory](doc/refer/memory-reference.md) | 压缩、结构化摘要、系统记忆 |
| [Tools](doc/refer/tools-reference.md) | 工具声明/注册/调用链 |
| [Search Guard](doc/refer/search-guard-reference.md) | 检索门禁、预算与自动扩容策略 |
| [Eval](doc/refer/eval-reference.md) | 判定模型、verifier 链路 |
| [Observability](doc/refer/observability-reference.md) | 事件模型、postmortem 生成 |
| [Agent 协同](doc/refer/agent-collaboration-reference.md) | 主从 Agent 协同与角色路由 |
| [配置](doc/refer/config-reference.md) | 模型配置、压缩配置、环境变量 |
