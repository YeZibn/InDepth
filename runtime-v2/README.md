# runtime-v2

## 项目定位

`runtime-v2/` 是 `InDepth` 中用于推进下一代 runtime 的独立工作区。

这里同时承载三类内容：

1. 设计文档
2. 开发进度记录
3. 新实现源码与测试

当前推进方式是：

1. 先完成设计收口
2. 再按步骤逐块落实现
3. 每落一个实现块，就补对应的实现说明

## 当前状态

当前状态如下：

1. `S1 ~ S12` 第一版子任务设计稿已全部落文档
2. `S13` 及后续增量设计模块已在 `design/` 下持续补充
3. 开发已完成模块 01 ~ 模块 24 的当前阶段实现
4. 当前代码已经具备最小可运行主链：
   - `prepare`
   - `execute / solver / react step`
   - `completion evaluator / reflexion`
   - `finalize / verifier`
5. `PreparePhase` 当前已经支持：
   - 初始 planning
   - 非空 graph 上的 replan 增量 planning
6. judge 型链路当前已经正式接入统一 prompt 模块：
   - `CompletionClaim -> CompletionEvaluator`
   - `Handoff -> RuntimeVerifier`

相关入口：

1. 总体设计计划：
   [runtime-v2-12-structure-implementation-plan-design-v1.md](/Users/yezibin/Project/InDepth/runtime-v2/design/runtime-v2-12-structure-implementation-plan-design-v1.md)
2. 开发进度记录：
   [development-progress.md](/Users/yezibin/Project/InDepth/runtime-v2/development-progress.md)
3. 实现说明目录：
   [implementation/README.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/README.md)

## 思想架构

`runtime-v2` 当前的总体思想可以压缩成 6 条：

1. 宿主层与 runtime core 解耦，宿主只负责会话、任务和启动新 run。
2. runtime 主链收敛为 `prepare -> execute step loop -> finalize`。
3. 正式状态结构收敛为极简 `RunContext`，避免把临时材料长期挂在主状态上。
4. `task graph` 是正式执行骨架，不再依赖隐式 todo/runtime 混合控制。
5. `subagent` 是受主 runtime 控制的 worker，必须绑定到显式 node。
6. 等待后继续推进统一收敛为“基于既有上下文重开新 run”。

## 目录结构

当前目录结构按“设计 + 说明 + 源码工作区”组织：

```text
runtime-v2/
  design/                 # 设计稿
  implementation/         # 各实现块说明文档
  src/rtv2/               # runtime-v2 独立源码包
  tests/                  # runtime-v2 独立测试
  development-progress.md
  README.md
```

`src/rtv2/` 下当前预留的子包包括：

1. `host`
2. `state`
3. `task_graph`
4. `orchestrator`
5. `tools`
6. `prompting`
7. `finalize`
8. `memory`
9. `subagent`

## 当前已落实现

当前已经落地并有实现说明的模块如下：

1. [implementation/state.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/state.md)
2. [implementation/host.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/host.md)
3. [implementation/task-graph.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/task-graph.md)
4. [implementation/orchestrator.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/orchestrator.md)
5. [implementation/memory.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/memory.md)
6. [implementation/prompting.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/prompting.md)
7. [implementation/prepare.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/prepare.md)
8. [implementation/react-step.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/react-step.md)
9. [implementation/skills.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/skills.md)
10. [implementation/solver.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/solver.md)
11. [implementation/finalize.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/finalize.md)

## 测试方式

当前可直接运行的最小测试命令：

```bash
python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_run_identity.py
```

## 环境配置

当前 `runtime-v2` 已有真实 LLM 接入，默认读取项目根下 `.env` 或系统环境变量。

建议先基于 [`.env.example`](/Users/yezibin/Project/InDepth/runtime-v2/.env.example) 创建本地 `.env`：

```bash
cp /Users/yezibin/Project/InDepth/runtime-v2/.env.example /Users/yezibin/Project/InDepth/runtime-v2/.env
```

当前最小必填项：

1. `LLM_MODEL_ID`
2. `LLM_API_KEY`
3. `LLM_BASE_URL`

当前这些组件会直接读取这组环境变量：

1. [src/rtv2/model/http_chat_provider.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/model/http_chat_provider.py)
2. [src/rtv2/solver/react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/react_step.py)
3. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)

说明：

1. `HttpChatModelProvider` 走 OpenAI-compatible `/chat/completions`
2. 若未安装 `python-dotenv`，代码仍可直接读取系统环境变量
3. 若缺少上述变量，provider 初始化会直接报错

## 开发约束

当前开发约束如下：

1. 按开发进度文档逐步推进，不一次性铺开实现。
2. 一次只落一个小任务，并和当前设计结论保持一致。
3. 若实现暴露出设计冲突，先统一口径，再继续写代码。
4. 当前实现代码默认先写在 `runtime-v2/src/rtv2/`，不直接混入旧 `app/core/runtime/`。
