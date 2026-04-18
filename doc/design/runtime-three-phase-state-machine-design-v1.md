# InDepth Runtime 三阶段状态机设计稿 V1

更新时间：2026-04-18  
状态：Draft

## 1. 背景

当前 Runtime 已经在 Todo 规划链路上完成了一轮收口：

1. `plan_task` 成为唯一对外 Todo 变更入口
2. `create/update` 已下沉为内部实现
3. Runtime 自动落盘路径已统一为调用 `plan_task`

但当前主链路仍有一个结构性问题：

1. `prepare` 仍然容易被理解成“一个前置工具”
2. 其职责边界和执行阶段混杂
3. `final`、`eval`、恢复摘要、最终输出之间的阶段关系不够显式
4. InDepth 主注入与阶段差异之间还没有清晰分层

因此，本稿提出将一次任务运行明确建模为三个 Runtime 阶段：

1. `preparing`
2. `executing`
3. `finalizing`

本稿的重点不是引入新的独立 Planning LLM，而是：

1. 保留同一主链路 LLM
2. 保留 InDepth 主注入
3. 通过 phase-specific overlay 明确当前状态
4. 让 Runtime 在单轮运行中只走一次三阶段

## 2. 目标

1. 将 `prepare` 从 tool 概念下沉为 Runtime phase
2. 保持同一主链路 LLM，避免上下文、经验记忆和风格断裂
3. 让 InDepth 主注入保持稳定，不因阶段切换被覆盖
4. 让 `plan_task` 继续作为唯一 Todo 落盘入口
5. 让现有 `eval` 成为 `finalizing` 阶段的核心判定步骤
6. 明确单轮任务只走一次：`preparing -> executing -> finalizing`

## 3. 非目标

1. 本稿不重写 InDepth 主注入内容
2. 本稿不重做 Todo markdown schema
3. 本稿不引入独立 planning LLM
4. 本稿不替换现有 eval orchestrator
5. 本稿不在同一轮运行中支持 `finalizing -> executing` 回跳

## 4. 核心判断

### 4.1 `prepare` 不是工具，而是阶段

`prepare` 一旦被做成普通 tool，系统心智会自然偏向：

1. 模型“先调一个 prepare 工具”
2. Runtime“在执行前插一个工具步骤”
3. 阶段边界重新退化为工具调用顺序

这不符合我们希望建立的任务生命周期模型。

因此：

1. tool 是 phase 内可调用的能力
2. phase 是 Runtime 自己维护的生命周期状态
3. `prepare` 属于后者，不属于前者

### 4.2 不引入独立 Planning LLM

本项目当前更重视：

1. 上下文连续性
2. 经验记忆继承
3. 用户偏好一致性
4. 同一任务周期内的统一决策口径

因此不建议把 planning 拆给另一个无工具 LLM。  
正确做法是：

1. 同一主链路 LLM
2. 同一 InDepth base injection
3. 在不同阶段叠加不同的状态确认 overlay

### 4.3 阶段差异主要来自“当前状态确认”

三个阶段不应通过三套互相替代的系统 prompt 来实现。  
更合理的做法是注入分层：

1. `InDepth Base Injection`
2. `Phase Overlay Injection`
3. `Runtime Context Injection`

其中 phase overlay 的主要作用不是重塑人格，而是明确告诉模型：

1. 你现在处于哪个阶段
2. 当前阶段目标是什么
3. 当前阶段不要做什么

### 4.4 单轮运行只走一次三阶段

为保证 Runtime 稳定性，本稿建议：

1. 每一轮 run 只走一次三阶段
2. `preparing -> executing -> finalizing`
3. 一旦进入 `finalizing`，本轮只做结算，不再回跳到 `executing`

如果需要继续执行，应在下一轮从 `preparing` 重新开始。

## 5. 设计原则

### 5.1 同一主链路 LLM

planning、execution、closeout 共用同一个主 LLM。

收益：

1. 上下文不被切断
2. memory recall 和 user preference recall 不需要二次拼装
3. todo / recovery / eval 的口径保持一致

### 5.2 InDepth 主注入稳定不变

InDepth 是身份层，而不是阶段层。

它负责：

1. agent 身份
2. 通用执行原则
3. 长期风格与安全边界
4. 对 todo / recovery / memory 的总体态度

这层在整个任务周期里应保持稳定。

### 5.3 Phase Overlay 只表达局部状态

phase overlay 负责表达：

1. 当前处于哪个阶段
2. 当前阶段的首要目标
3. 当前阶段禁止的行为倾向

这层必须简短、稳定、低侵入。

### 5.4 Runtime Context 是动态事实层

动态上下文包括：

1. 用户当前输入
2. active todo context
3. active todo 全文
4. latest recovery
5. memory recall
6. user preference recall

这层由 Runtime 注入，不属于 prompt 角色定义。

## 6. 注入分层模型

最终系统提示不应是“三套不同人格 prompt”，而应是：

`InDepth Base Injection + Phase Overlay Injection + Runtime Context Injection`

### 6.1 Base Injection

稳定不变，继续沿用当前 InDepth 主注入。

### 6.2 Preparing Overlay

建议表达为：

1. 你当前处于 `preparing`
2. 当前目标是理解任务、判断 todo 需求、形成执行骨架
3. 不要在该阶段展开大规模执行

### 6.3 Executing Overlay

建议表达为：

1. 你当前处于 `executing`
2. 当前目标是推进任务、使用工具、更新 todo、完成交付
3. 不要无故回到大范围重新规划

### 6.4 Finalizing Overlay

建议表达为：

1. 你当前处于 `finalizing`
2. 当前目标是基于已有结果做评估、总结和收尾
3. 不要在该阶段继续扩张任务范围

## 7. 三阶段状态机

### 7.1 Preparing

#### 进入时机

1. 新任务开始
2. 用户补充信息后恢复继续
3. 上一轮结束后新一轮 run 开始

#### 职责

1. 注入 InDepth base prompt
2. 注入 preparing overlay
3. 注入当前任务事实
4. 判断是否需要 todo
5. 若需要，生成完整 todo plan
6. 由 Runtime 自动调用 `plan_task`
7. 决定是否进入 `executing`

#### 输出 contract

建议固定为：

```json
{
  "should_use_todo": true,
  "task_name": "string",
  "context": "string",
  "split_reason": "string",
  "subtasks": [
    {
      "name": "string",
      "description": "string",
      "split_rationale": "string",
      "dependencies": ["optional task number strings"],
      "acceptance_criteria": ["optional string array"]
    }
  ],
  "notes": ["string"]
}
```

#### 不再保留

1. `plan_ready`
2. `recommended_mode`
3. `recommended_update_task_args`

#### 到 `executing` 的切换条件

只允许两类出口：

1. `should_use_todo = false`
2. `should_use_todo = true` 且 `plan_task` 成功

否则本轮不能进入执行态。

#### CLI 可见输出

prepare 完成后、进入 `executing` 前，Runtime 应向 CLI 输出一段简短但完整的 `[Prepare]` 摘要，至少包含：

1. `任务目标`
2. `决策`
3. `下一阶段`
4. 顶层 `拆分理由`
5. `计划摘要`
6. `计划明细`（完整子任务列表）
7. 每条子任务的 `拆分依据`

### 7.2 Executing

#### 进入时机

1. prepare 成功结束
2. todo 如有需要已完成落盘
3. 当前执行骨架已明确

#### 职责

1. 正常调用工具推进任务
2. 更新 todo
3. 处理 recovery
4. 生成产物
5. 积累完成证据

#### 边界

1. 可以正常执行工具
2. 不应在无阻塞情况下重新展开大范围 planning
3. 不应把“是否启用 todo”重新当作开放问题

### 7.3 Finalizing

#### 进入时机

1. 模型声称任务已完成
2. Runtime 停止继续执行
3. 工具失败导致本轮需要收口
4. 用户要求先总结或先到这里

#### 职责

1. 汇总执行证据
2. 调用现有 `eval`
3. 判定最终状态
4. 生成恢复摘要
5. 生成最终用户输出
6. 更新 runtime 状态
7. 做 postmortem / memory closeout
8. 由统一 finalizing pipeline 分流 `paused closeout` 与 `completed closeout`

#### 关键约束

1. 进入 `finalizing` 后，本轮不再回跳 `executing`
2. 若需要继续执行，应在下一轮从 `preparing` 重新进入

## 8. 阶段与 Prompt 注入保留规则

### 8.1 基本原则

phase 切换时，只应更新 phase overlay，不应抹掉已经注入的动态上下文。

这里的动态上下文包括：

1. system memory recall block
2. user preference recall block
3. prepare phase 附加说明
4. 其他 runtime 在本轮已确认并注入的轻量事实块

### 8.2 更新方式

推荐做法是：

1. 将 system prompt 视为 `base prompt + dynamic injected context`
2. phase 切换时只替换 `base prompt` 中的 phase overlay
3. 保留后缀中的动态注入内容

不推荐做法是：

1. 在 phase 切换时整块重建第一条 system message
2. 造成 recall block / preference block / prepare block 丢失

### 8.3 原因

因为 phase 的职责是确认当前状态，而不是清空本轮已经获得的上下文事实。

如果 phase 切换导致动态注入丢失，会直接带来：

1. recall 命中后又失效
2. 用户偏好在首轮可见、切换后不可见
3. prepare 输出的约束与建议被后续执行态覆盖

## 9. 阶段与工具/技能的关系

### 9.1 总原则

不同阶段底层可接入的工具和技能集合可以保持一致，但阶段策略不一样。

也就是说：

1. 不必为每个阶段维护三套独立 registry
2. 阶段差异主要通过 prompt / phase overlay 约束
3. Runtime 不应长期维护大份 phase 工具硬白名单

### 9.2 Preparing

`preparing` 的目标是思考和定骨架，不是展开执行。

因此在该阶段：

1. 主链路不应自由调用外部执行工具
2. todo 判断和计划生成应由 runtime 内部 prepare 机制完成
3. skills 不应在该阶段被展开为实际执行流程

但这并不等于 `preparing` 必须完全失去能力。

更合理的做法是：

1. 允许少量“观察类 / 判断类”能力
2. 避免“执行类 / 产出类 / 改写类”能力被滥用
3. 主要通过 prompt 明确约束，而不是靠硬编码白名单

#### 建议白名单

`preparing` 可以有限使用以下能力：

1. 回看当前会话历史
2. 查看当前时间
3. 读取 runtime 已注入的 active todo / latest recovery / memory recall / user preference recall
4. 查询当前 todo 进度或当前绑定状态这类只读信息
5. 必要时读取少量本地上下文事实，但不得在该阶段展开大范围探索

#### 明确禁止

`preparing` 不应做以下事情：

1. 大规模读文件、搜目录、跑环境探测
2. 生成最终产物
3. 调用会修改外部状态的工具
4. 启动真正的子任务执行链
5. 把 skills 展开成完整执行流程

#### 设计意图

也就是说，`preparing` 应当具有“看”和“判断”的权利，但不应具有“广泛执行”和“持续推进”的权利。

换言之，`preparing` 更接近“可见状态机阶段”，而不是“开放工具执行阶段”。

### 9.3 Executing

`executing` 是主要的工具与技能使用阶段。

因此在该阶段：

1. 工具可正常使用
2. skills 可正常参与任务推进
3. todo / recovery /产物生成都在该阶段发生

### 9.4 Finalizing

`finalizing` 的目标是收尾，不是继续扩张执行。

因此在该阶段：

1. 不应重新开放大范围工具执行
2. 不应把 skills 再次展开成新的主执行链
3. 允许内部 closeout、verification、postmortem、memory finalize 等收尾动作

### 9.5 结论

因此，“不同阶段可以用的工具和技能一样吗”的正确答案不是简单的“是”或“不是”，而是：

1. 底层能力集合可以一样
2. 但阶段使用权限、使用目的和使用强度必须不同
3. 真正的差异应由 phase policy 控制，而不是靠复制三套工具定义来实现

## 10. `plan_task`、`eval`、`final` 的关系

### 10.1 `plan_task`

定位：

1. 不是 planning 本身
2. 而是 `preparing -> executing` 的桥
3. 是唯一 Todo 落盘入口

职责：

1. 校验 prepare 产出的 todo 计划
2. 内部决定 create / update
3. 执行真实落盘

### 10.2 `eval`

定位：

1. 不是独立 phase
2. 是 `finalizing` 阶段内部的核心判定器
3. 与主链路 LLM 保持独立，不复用主链路的执行上下文叙事

职责：

1. 基于证据判断任务是否真的完成
2. 检查 overclaim
3. 识别 failure type / known gaps / recoverability

设计原则：

1. `preparing / executing / finalizing` 由同一个主链路 LLM 驱动
2. `eval` 继续由独立判定组件承担
3. 不让主链路 LLM 直接充当自己的最终裁判

### 10.3 现有 `final`

定位调整为：

1. 不再视为“执行后的杂项函数”
2. 而是 `finalizing pipeline` 的一部分

即：

`finalizing = gather evidence + eval + status resolution + closeout`

## 11. 与现有实现的映射

### 11.1 当前可以直接复用的部分

1. `plan_task` 单入口
2. `create/update` 已内部化
3. 现有 eval orchestrator
4. verification handoff
5. postmortem / memory closeout

### 11.2 需要调整定位的部分

1. `prepare_task`
   - 口径上不再视为外部 tool
   - 当前仅作为 runtime 内部 fallback / 历史兼容层看待

2. `_run_prepare_phase(...)`
   - 从“前置调用 hidden tool”演进为真正的 phase 入口

3. `final`
   - 重定位为 `finalizing pipeline` 的组成部分

## 10. 运行流程

建议流程如下：

1. 用户输入进入 Runtime
2. Runtime 恢复 active todo / recovery / memory
3. 进入 `preparing`
4. 注入 preparing overlay
5. 主 LLM 产出 prepare result
6. 若需要 todo，则 Runtime 自动调用 `plan_task`
7. 满足切换条件后进入 `executing`
8. 执行工具调用、todo 推进、恢复
9. 本轮停止推进后进入 `finalizing`
10. finalizing 内部调用 eval
11. 根据结果输出：
   - completed
   - failed
   - partial / recoverable

## 11. 落地顺序

### 第一步：口径统一

1. 在文档和注释中统一：
   - `prepare` 是 phase
   - `plan_task` 是唯一 Todo tool
   - `eval` 属于 finalizing 内部步骤

### 第二步：显式 phase 状态

在 Runtime 中引入显式阶段：

1. `preparing`
2. `executing`
3. `finalizing`

### 第三步：phase overlay 注入

实现三套轻量 overlay：

1. preparing overlay
2. executing overlay
3. finalizing overlay

### 第四步：prepare contract 固定

让 prepare 结果收口到统一结构，并由 Runtime 自动衔接 `plan_task`。

### 第五步：finalizing pipeline 对齐

将现有 final、eval、recovery summary、postmortem 重新组织成显式的 finalizing 流程。

## 12. 验收口径

满足以下条件视为设计落地：

1. `prepare` 不再被建模为模型自由调用的普通 tool
2. 主链路只使用同一个 LLM
3. InDepth 主注入保持稳定不变
4. phase 差异通过 overlay 表达，而非替换整套人格 prompt
5. `plan_task` 仍是唯一 Todo 落盘入口
6. `eval` 成为 finalizing 阶段的核心判定步骤
7. `eval` 继续独立于主链路 LLM，不与执行叙事共用判定角色
8. 单轮 run 只走一次：`preparing -> executing -> finalizing`

## 13. 一句话总结

本稿的核心不是增加一个 prepare 工具，也不是拆出一个独立 planning LLM，  
而是在同一主链路 LLM、同一套 InDepth 主注入之上，引入三阶段 Runtime 状态机，并通过阶段状态确认 overlay 来明确每个阶段的行为边界。
