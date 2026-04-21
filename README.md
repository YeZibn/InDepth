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
- **User preference memory 记录用户偏好，实现个性化服务**
- 记忆事件（triggered/retrieved/decision）进入观测链路

**三层记忆的分工**：

| 记忆类型 | 解决什么问题 | 典型数据 | 存储方式 |
|---------|-------------|---------|---------|
| **Runtime Memory** | 上下文爆炸 | 对话历史、决策、约束 | SQLite（按 Agent 类型分库） |
| **System Memory** | 经验复用 | 任务经验卡、最佳实践 | SQLite（统一存储） |
| **User Preference** | 个性化服务 | 用户兴趣、角色、习惯 | Markdown（单文件） |

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
- Runtime 澄清收束：恢复执行前，会先把旧计划中未完成的 subtasks 标记为 `abandoned`
- Runtime Todo 绑定感知：维护 `todo_id/active_subtask_number/execution_phase/binding_required`
- Runtime Prepare 现状感知：当存在 active todo 时，prepare 会补充当前进度、未完成项和已知产物摘要
- Tool 体系：统一声明、注册、参数校验、调用封装
- SubAgent 协同：角色化子代理与并行执行
- Skills 统一接入：`build_skills_manager` + `<skills_system>` + 技能访问工具（按需读取 instructions/references/scripts）
- Todo 编排：统一 `todo_id` 语义，避免与 Runtime `task_id` 混淆，并以 subtask 作为最小执行/协作单元；Runtime 会在普通工具调用未绑定 active subtask 时暴露 warning
- Eval 判定：deterministic verifier + 可选 LLM judge
- Observability：事件落盘、指标聚合、postmortem
- Memory 闭环：运行时压缩摘要 + 系统经验卡沉淀

## 4. 快速开始

### 4.1 安装与运行

1. 安装依赖
   - `pip install -r requirements.txt`
2. 配置模型环境变量
   - 必填：`LLM_MODEL_ID`、`LLM_API_KEY`、`LLM_BASE_URL`
   - 可选：`LLM_MODEL_MINI_ID`（未设置时回退到 `LLM_MODEL_ID`）
   - System Memory 向量召回可选：
     `LLM_EMBEDDING_MODEL_ID`、`LLM_EMBEDDING_API_KEY`、`LLM_EMBEDDING_BASE_URL`、`ENABLE_SYSTEM_MEMORY_VECTOR_RECALL`、`SYSTEM_MEMORY_MILVUS_URI`
   - 缺失任一必填项会在启动时抛出 `ValueError`
   - 可参考项目根目录 `.env.example`
3. 启动 CLI
   - `python app/agent/runtime_agent.py`
   - 默认加载 `app/skills/` 下全部技能（当前为 `memory-knowledge-skill`、`ppt-skill`、`skill-creator`）
4. 检查向量召回依赖是否就绪
   - `python scripts/check_system_memory_vector_recall.py`
5. 常用 CLI 命令
   - `/help`：查看命令帮助
   - `/task <label>`：结束当前任务并启动下一任务
   - `/newtask <label>`：`/task` 的别名
   - `/new [label]`：结束当前任务并启动下一任务
   - `/status`：查看当前模式（固定 `task`）与 `task_id`
   - `/exit`：退出

### 4.1.1 System Memory 向量召回配置示例

当前实现支持把主 LLM 与 embedding 通道拆开配置。

示例：

```bash
LLM_MODEL_ID=gpt-5.4
LLM_MODEL_MINI_ID=gpt-5.4-mini
LLM_API_KEY=...
LLM_BASE_URL=https://kuaipao.ai/v1

LLM_EMBEDDING_MODEL_ID=Qwen/Qwen3-Embedding-8B
LLM_EMBEDDING_API_KEY=...
LLM_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1

ENABLE_SYSTEM_MEMORY_VECTOR_RECALL=true
SYSTEM_MEMORY_MILVUS_URI=http://127.0.0.1:19530
SYSTEM_MEMORY_MILVUS_COLLECTION=system_memory_card_embedding
SYSTEM_MEMORY_EMBEDDING_DIM=4096
SYSTEM_MEMORY_VECTOR_TOP_N=10
SYSTEM_MEMORY_RECALL_TOP_K=5
SYSTEM_MEMORY_RECALL_MIN_SCORE=0.65
```

说明：
- 推荐为 embedding 使用独立 provider，而不是复用主 LLM 通道。
- `Qwen/Qwen3-Embedding-8B` 当前实测返回向量维度为 `4096`，因此 `SYSTEM_MEMORY_EMBEDDING_DIM` 应配置为 `4096`。
- Milvus 本地默认监听 `http://127.0.0.1:19530`。
- 若 Milvus 开启鉴权，可额外配置 `SYSTEM_MEMORY_MILVUS_TOKEN`。

### 4.1.2 向量召回自检

项目提供了一个最小自检脚本：

- `python scripts/check_system_memory_vector_recall.py`

脚本会自动读取项目根目录 `.env`，依次检查：
1. 向量召回配置是否开启
2. embedding provider 是否可用
3. embedding 请求是否成功
4. Milvus collection 是否可访问

当前实现已验证：
- 可使用独立 embedding 通道访问 SiliconFlow
- 可连接本地 Milvus
- 可完成 `embedding + Milvus search` 的最小链路

### 4.2 运行模式说明（Runtime CLI）

- 当前仅支持 `task` 单模式（启动即进入 `task`）
- 普通输入统一走执行链路，不再区分 chat/task 的工具可用性
- 在首轮执行前，CLI 会先打印一段 `[Prepare]` 摘要，展示：
  - 任务目标
  - 是否启用或沿用 todo
  - 下一阶段
  - 顶层拆分理由
  - 当前现状摘要（仅 active todo 存在时）
  - 完整子任务清单（含每条拆分依据）
- 当 Runtime 进入 `awaiting_user_input`：
  - CLI 会提示 `[需要澄清]`
  - 用户下一次正常输入会沿用同一 `run_id` 恢复执行
  - 若存在 active todo，恢复前会先把旧计划中未完成的 subtasks 标记为 `abandoned`
  - 空输入不会触发模型调用

### 4.3 配置速查（压缩相关，可选）

| 环境变量 | 默认值 | 作用 |
|----------|--------|------|
| `ENABLE_MID_RUN_COMPACTION` | `True` | 是否启用运行中压缩 |
| `COMPACTION_MIDRUN_TOKEN_RATIO` | `0.82` | mid-run 压缩 token 阈值 |
| `COMPACTION_TOOL_BURST_THRESHOLD` | `5` | 单次 `tool_calls` 条目触发阈值 |
| `MODEL_CONTEXT_WINDOW_TOKENS` | `160000` | 模型理论上下文窗口 |
| `COMPACTION_TRIGGER_WINDOW_TOKENS` | `120000` | Runtime 压缩触发预算窗口 |
| `ENABLE_FINALIZE_COMPACTION` | `False` | 是否在任务结束后执行 destructive finalize 压缩 |
| `COMPACTION_CONTEXT_WINDOW_TOKENS` | `-` | 兼容保留旧字段；未配置新字段时作为双窗口回退值 |
| `COMPACTION_CONSISTENCY_GUARD` | `True` | 一致性守护开关 |
| `COMPACTION_TARGET_KEEP_RATIO_MIDRUN` | `0.40` | midrun 压缩后目标保留比例 |
| `COMPACTION_TARGET_KEEP_RATIO_FINALIZE` | `0.40` | finalize 压缩后目标保留比例 |
| `COMPACTION_MIN_KEEP_TURNS` | `3` | 压缩后至少保留最近 3 轮原文 |
| `COMPACTION_COMPRESSOR_KIND` | `auto` | 压缩器类型：`auto / rule / llm` |
| `COMPACTION_COMPRESSOR_LLM_MAX_TOKENS` | `1200` | LLM 压缩摘要生成 token 上限 |
| `COMPACTION_EVENT_SUMMARIZER_KIND` | `auto` | `event` 工具链替代摘要器类型：`auto / rule / llm` |
| `COMPACTION_EVENT_SUMMARIZER_MAX_TOKENS` | `280` | `event` 工具链 mini 摘要生成 token 上限 |

压缩器说明：
- `auto`：真实模型默认使用 LLM 压缩；`MockModelProvider` 自动回退到规则压缩，方便测试稳定复现
- `rule`：始终使用现有规则压缩器
- `llm`：优先使用 LLM 压缩；若模型报错、输出非 JSON 或一致性校验失败，则自动回退到规则压缩
- `midrun/finalize` 路径使用 `COMPACTION_COMPRESSOR_*` 控制结构化摘要压缩
- `MODEL_CONTEXT_WINDOW_TOKENS` 表示模型能力上限；`COMPACTION_TRIGGER_WINDOW_TOKENS` 表示 Runtime 何时开始认为“接近压缩风险”
- `event` 路径使用独立的 `COMPACTION_EVENT_SUMMARIZER_*` 控制工具链替代摘要；真实运行时默认优先使用 mini 模型，失败回退规则摘要

### 4.4 关键目录

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

### 4.5 默认工具能力（简版）

| 类别 | 关键工具 | 用途 |
|------|---------|------|
| 基础执行 | `bash`、`read_file`、`write_file`、`get_current_time` | 命令执行与文件操作 |
| 检索门禁 | `init_search_guard`、`guarded_ddg_search`、`update_search_progress`、`build_search_conclusion` | 受控检索与预算治理 |
| 子代理协同 | `create_sub_agent`、`run_sub_agent`、`run_sub_agents_parallel` | 角色化并行执行 |
| Todo 编排 | `plan_task`、`update_task_status`、`append_followup_subtasks`、`get_next_task`、`generate_task_report` | 以 `plan_task` 作为对外主入口的子任务管理、状态流转与进度跟踪 |
| 记忆工具 | `search_memory_cards`、`get_memory_card_by_id` | 只读经验检索与按需展开 |

### 4.6 观测与产物落点

- 全量事件流（JSONL）：`app/observability/data/events.jsonl`
- 记忆事件与经验卡（SQLite）：`db/system_memory.db`
- 每次运行复盘目录：`observability-evals/<task_id>__<run_id>/`
- 复盘主文件：`observability-evals/<task_id>__<run_id>/postmortem.md`

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
     - 在运行中触发上下文压缩，在结束时进入显式 finalizing 双 step
     - `finalizing(answer)` 面向用户产出最终回答
     - `finalizing(handoff)` 面向系统产出结构化 handoff
   - 输出：`final_answer`、`verification_handoff`、`stop_reason`、运行状态，以及后续评估所需执行证据。

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
     - subtask 约束：以“单一可验证动作”为粒度；未完成项不得伪装为 `completed`
     - 绑定感知：Runtime 会维护 active subtask 上下文；当 todo 已创建但普通工具调用尚未绑定 active subtask 时，会发出 warning 事件；若此时失败，会进入 `orphan failure`
     - 并行协同：SubAgent 角色化执行（researcher/builder/reviewer/verifier）
     - 经验检索：`search_memory_cards` / `get_memory_card_by_id` 提供只读 system memory 访问；运行中候补记忆不再是默认主链路能力
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
   - 作用：让系统具备"经验可积累、后续可复用"的长期能力。
   - 关键模块：
     - Runtime memory：`app/core/memory/sqlite_memory_store.py`
     - 压缩器：`app/core/memory/context_compressor.py`
     - System memory：`app/core/memory/system_memory_store.py`
     - **用户偏好：`app/core/memory/user_preference_store.py`（新增）**
   - 主要机制：
     - 运行中压缩分两路：`token` 触发写入 `summary_json`；`event` 触发将连续工具调用段替换为单条摘要消息（状态工具豁免、保留最近工具单元）
     - 任务开始前执行 system memory 轻量召回，注入 `memory_id + recall_hint`，必要时再按 id 拉取完整卡片
     - Finalizing 显式拆成 `answer -> handoff` 双 step，handoff 成为 verification 与 memory 的共同事实源
     - 任务结束后仅从 `verification_handoff.memory_seed` 沉淀正式经验卡（`memory_card`）
     - `memory_card` 当前简化为 `id/title/recall_hint/content/status/updated_at/expire_at`
     - 记忆事件（triggered/retrieved/decision）进入 observability 链路；事件表保留，主卡表简化
     - **用户偏好记忆：Markdown 单文件存储，支持置信度与来源追踪，用于个性化提示词注入**
   - 输出：结构化历史摘要、系统经验卡、**用户偏好画像**、可统计的记忆治理数据。

### 5.1 System Architecture

![InDepth System Architecture](doc/assets/readme/architecture-paper-style.svg)

## 6. 参考文档

详细实现说明在 `doc/refer/`：

| 文档 | 说明 |
|------|------|
| [总索引](doc/refer/README.md) | 文档索引与阅读顺序 |
| [架构总览](doc/refer/architecture-reference.md) | 系统架构、模块职责、交互流程 |
| [Runtime](doc/refer/runtime-reference.md) | AgentRuntime 主循环、收敛逻辑 |
| [Prompt](doc/refer/prompt-reference.md) | Prompt 组装、运行时注入顺序、主/子 Agent 提示词来源 |
| [Skills](doc/refer/skills-reference.md) | 技能加载、`<skills_system>` 注入、技能访问工具 |
| [Memory](doc/refer/memory-reference.md) | 压缩、结构化摘要、系统记忆 |
| [Runtime Memory](doc/refer/runtime-memory-reference.md) | 当前 task 会话记忆、上下文压缩、step token ledger 与预算语义 |
| [System Memory](doc/refer/system-memory-reference.md) | 跨任务经验卡、召回链路、finalize 沉淀与 recall 注入 |
| [**User Preference**](doc/refer/user-preference-reference.md) | **用户偏好记忆存储、API 与使用场景（新增）** |
| [Tools](doc/refer/tools-reference.md) | 工具声明/注册/调用链 |
| [Todo](doc/refer/todo-reference.md) | Todo 编排、subtask 设计、依赖流转、与 SubAgent 协作边界 |
| [Subtask Status](doc/refer/subtask-status-reference.md) | 当前如何选择应执行的 subtask，以及三种基础更新动作与状态联动 |
| [Search Guard](doc/refer/search-guard-reference.md) | 检索门禁、预算与自动扩容策略 |
| [Eval](doc/refer/eval-reference.md) | 判定模型、verifier 链路 |
| [Observability](doc/refer/observability-reference.md) | 事件模型、postmortem 生成 |
| [Agent 协同](doc/refer/agent-collaboration-reference.md) | 主从 Agent 协同与角色路由 |
| [配置](doc/refer/config-reference.md) | 模型配置、压缩配置、环境变量 |

## 7. 常用测试入口

- 运行全部测试：`python -m pytest -q`
- Runtime 关键链路：`python -m pytest -q tests/test_runtime_eval_integration.py tests/test_runtime_context_compression.py`
- Todo 编排链路：`python -m pytest -q tests/test_runtime_todo_recovery_integration.py tests/test_todo_recovery_flow.py`
- 工具与协同：`python -m pytest -q tests/test_sub_agent_tool.py tests/test_sub_agent_role_tools.py`
- 检索门禁自动扩容：`python -m pytest -q tests/test_search_guard_auto_override.py`

补充说明：
- 若本地已安装 `pytest`，也可以用 `pytest` 运行同一批测试文件
- 当前仓库中没有 `tests/test_tool_registry.py`，旧 README 中该示例已移除
