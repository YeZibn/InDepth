# S3-T2 RuntimeOrchestrator 定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S3-T2`

## 1. 目标

`runtime-v2` 的主控对象统一命名为 `RuntimeOrchestrator`。

它的目标不是承载所有逻辑，而是作为一次 run 的唯一编排入口，负责：

1. 持有 run 级上下文
2. 驱动 phase 切换
3. 协调 task graph、tool、model、verification 等结构
4. 收敛一次运行的最终结果

## 2. 设计结论

基于当前对接结果，`S3-T2` 的正式结论如下：

1. v2 主控对象名为 `RuntimeOrchestrator`
2. 采用混合式结构：核心编排类 + phase/step 组件
3. `PreparePhase`、`FinalizePhase` 采用“类对象，但尽量无状态”的风格
4. `RunContext` 由 orchestrator 持有，并在 phase 间传递
5. orchestrator 第一版直接知道 `task graph`，不额外抽象成更高一层 execution engine

## 3. 结构定义

## 3.1 RuntimeOrchestrator

`RuntimeOrchestrator` 是 v2 的 run 级主控类。

它负责：

1. 接收外部输入并创建一次 run
2. 初始化 `RunContext`
3. 按顺序调用：
   - `PreparePhase`
   - `ExecutePhase`
   - `FinalizePhase`
4. 协调依赖对象
5. 返回最终 `RunOutcome`

它不负责：

1. 自己维护复杂的 task graph 状态推进细节
2. 自己实现 tool 领域逻辑
3. 自己实现 verification 规则
4. 自己承载 memory 召回细节
5. 自己直接拼接所有 prompt 细节

一句话说，`RuntimeOrchestrator` 是编排中心，不是上帝对象。

## 3.2 Phase / Step 组件

v2 第一版采用：

1. `PreparePhase`
2. `ExecutePhase`
3. `FinalizePhase`

其中正式区别如下：

1. `PreparePhase` 与 `FinalizePhase` 保持 phase 对象风格
2. `ExecutePhase` 不再理解为“一整段 `run(ctx)`”
3. `ExecutePhase` 的正式定位是围绕当前 active node 运行一轮 step 的执行阶段组件

### `PreparePhase`

建议接口方向：

```python
class PreparePhase:
    def run(self, ctx: RunContext) -> RunContext: ...
```

### `ExecutePhase`

建议接口方向：

```python
class ExecutePhase:
    def run_step(self, ctx: RunContext) -> StepResult: ...
```

### `FinalizePhase`

建议接口方向：

```python
class FinalizePhase:
    def run(self, ctx: RunContext) -> RunOutcome: ...
```

第一版不要求这里的签名立刻最终定死，但方向应该稳定：

1. `Prepare` 负责建立可执行入口
2. `Execute` 负责 step loop 中的一轮 step 产出
3. `Finalize` 负责 closeout 入口与 `RunOutcome` 收口

## 3.3 RunContext 持有方式

`RunContext` 由 `RuntimeOrchestrator` 持有。

采用的模式是：

1. orchestrator 创建 `RunContext`
2. prepare/finalize 接收 `RunContext`
3. execute 围绕 `RunContext` 产出 `StepResult`
4. orchestrator 始终是 run 级 context 的唯一拥有者

这里不采用“每个 phase 自己持有一份独立上下文”的设计，原因是：

1. v2 的核心就是统一状态流
2. task graph、verification、events、memory 都需要围绕同一个 run context 对齐
3. 如果 phase 或 execute 组件自己持有主状态，容易重新回到隐式耦合

## 3.4 Task Graph 的地位

第一版中，`RuntimeOrchestrator` 直接知道 `task graph`。

结论是：

1. 不额外抽象一个比 `task graph` 更高的 `execution engine`
2. `task graph` 作为 v2 的正式执行骨架，直接进入 orchestrator 依赖

这样做的原因是：

1. 当前系统的 todo 已经在事实上承担执行图角色
2. 第一版最重要的是把主干立住，而不是继续做抽象套抽象
3. 等 task graph 稳定后，如果确有必要，再考虑上提抽象层

## 4. 建议依赖边界

`RuntimeOrchestrator` 第一版建议直接依赖以下结构：

1. `RunContext`
2. `PreparePhase`
3. `ExecutePhase`
4. `FinalizePhase`
5. `TaskGraphState` 或 task graph service
6. tool registry / tool gateway
7. model gateway
8. verification gateway
9. observability/event emitter

其中建议避免的依赖方式：

1. 不直接依赖具体 sqlite store 实现
2. 不直接依赖具体 todo markdown 文件实现
3. 不直接依赖 verifier 内部细节
4. 不把 memory 召回逻辑写回 orchestrator 内部

## 5. 最小骨架建议

`RuntimeOrchestrator` 第一版最小骨架可理解为：

```text
RuntimeHost
  -> RuntimeOrchestrator.run(...)
      -> build RunContext
      -> PreparePhase.run(ctx)
      -> while execute:
           step_result = ExecutePhase.run_step(ctx)
           ctx = apply_step_result(ctx, step_result)
         end
      -> FinalizePhase.run(ctx)
      -> return RunOutcome
```

这就是后续 `S3-T5` runtime skeleton 的直接目标。

## 6. 与其他任务的对接关系

`S3-T2` 直接依赖：

1. `S4-T2` 核心状态对象集合
2. `S5-T2` task graph 命名决策
3. `S6-T2` tool 协议
4. `S1-T2` prompt 分层结构

`S3-T2` 直接服务：

1. `S3-T3` phase engine 接口
2. `S3-T4` step loop 最小职责
3. `S3-T5` runtime skeleton
4. `S2-T2` runtime host 接口

## 7. 本任务结论摘要

本任务的最终结论可以压缩成 5 句话：

1. v2 主控对象统一叫 `RuntimeOrchestrator`
2. 结构采用“核心编排类 + phase/step 组件”的混合式
3. `Prepare/Finalize` 保持 phase 对象风格，`Execute` 负责 step loop 中的一轮 step
4. `RunContext` 由 orchestrator 持有并贯穿整个 run
5. 第一版 orchestrator 直接知道 `task graph`
