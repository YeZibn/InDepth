# S8-T2 Runtime Memory 模型（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 runtime memory 的正式模型。

目标是：

1. 明确 runtime memory 在 `S8` 中的定位
2. 明确 runtime memory 与 `RunContext` 的边界
3. 明确 runtime memory 作为处理器的输入输出
4. 明确 runtime memory 如何进入 prompt

## 2. 正式结论

本任务最终结论如下：

1. runtime memory 是 `S8` 的正式主位之一
2. runtime memory 作为处理器存在
3. runtime memory 不作为 `RunContext` 的一级正式状态块存在
4. runtime memory 的产物直接进入 prompt
5. 第一版输出继续采用旧模式：
   - `prompt_context_text`

## 3. Runtime Memory 的定位

runtime memory 在 v1 中的定位是：

1. 处理当前 run 的运行期上下文材料
2. 为每次模型调用生成可继续推进的上下文文本

它不是：

1. 长期记忆存储
2. 用户偏好存储
3. `RunContext` 正式状态容器

## 4. 与 RunContext 的关系

本任务明确规定：

1. `RunContext` 保存正式运行状态
2. runtime memory 负责处理运行期上下文材料
3. `RunContext` 不保存大段运行期上下文正文
4. runtime memory 不直接并入 `RunContext`

也就是说：

1. `RunContext` 负责“系统现在是什么状态”
2. runtime memory 负责“prompt 现在该带什么上下文”

## 5. Runtime Memory 的最小输入

第一版最小输入如下：

1. `task_id`
2. `run_id`
3. `current_phase`
4. `active_node_id`
5. `user_input`
6. `compression_state`

## 6. Runtime Memory 的最小输出

第一版最小输出如下：

1. `prompt_context_text`

本任务明确规定：

1. 第一版不输出结构化 context blocks
2. 第一版继续采用旧模式文本产物

## 7. Runtime Memory 处理内容

runtime memory 第一版主要处理：

1. messages
2. summaries
3. compaction / compression 结果
4. resume 所需上下文材料

其核心目标是：

1. 让主链路可以持续装配 prompt
2. 让 run 可以恢复和续跑

## 8. 与 Compression 的关系

本任务与 `compression_state` 对齐如下：

1. `compression_state` 属于正式运行状态
2. runtime memory 消费 `compression_state`
3. runtime memory 处理压缩后的上下文材料

这意味着：

1. `compression_state` 记录“当前压缩状态是什么”
2. runtime memory 处理“压缩后的上下文怎么进入 prompt”

## 9. 挂点

runtime memory 的统一挂点是：

```text
run-progress / step-prep
  -> runtime memory processor
```

这意味着：

1. 它不在 run 开始一次性完成
2. 它在运行过程中持续服务主链路

## 10. 与 Prompt 的关系

本任务明确规定：

1. runtime memory 的产物直接进入 prompt assembly
2. 它不是主状态对象
3. 它服务当前 step 的上下文装配

## 11. 第一版边界

第一版明确不建议：

1. 把 runtime memory 整体挂进 `RunContext`
2. 让 runtime memory 直接承担长期记忆职责
3. 让 runtime memory 直接承担用户偏好职责
4. 在第一版就把输出强制升级成结构化 blocks

## 12. 对其他任务的直接输入

`S8-T2` 直接服务：

1. `S8-T7` memory domain 总设计
2. `S1-T4` prompt / state 边界
3. `S4-T4` 极简 RunContext
4. `S7-T5` context budget 策略

同时它直接依赖：

1. `S8-T1` runtime memory 现状清单
2. `S8-T7` memory domain 重设计

## 13. 本任务结论摘要

可以压缩成 5 句话：

1. runtime memory 是 `S8` 的正式主位之一
2. 它作为处理器存在，不作为 `RunContext` 状态块存在
3. 它消费运行期上下文材料并生成 `prompt_context_text`
4. 它主要挂在 step 前的上下文处理阶段
5. 它与长期记忆层和用户偏好层分工明确
