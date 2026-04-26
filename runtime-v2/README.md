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
2. 开发已进入 Step 02
3. 当前已落地的最小实现只有状态层第一项：`RunIdentity`

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

当前已经落地的实现块如下：

1. 状态层：
   [implementation/state.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/state.md)

当前实际代码文件：

1. [src/rtv2/state/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/state/models.py)
2. [tests/test_run_identity.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_run_identity.py)

## 测试方式

当前可直接运行的最小测试命令：

```bash
python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_run_identity.py
```

## 开发约束

当前开发约束如下：

1. 按开发进度文档逐步推进，不一次性铺开实现。
2. 一次只落一个小任务，并和当前设计结论保持一致。
3. 若实现暴露出设计冲突，先统一口径，再继续写代码。
4. 当前实现代码默认先写在 `runtime-v2/src/rtv2/`，不直接混入旧 `app/core/runtime/`。
