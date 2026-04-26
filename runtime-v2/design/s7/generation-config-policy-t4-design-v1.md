# S7-T4 Generation Config 归属与规则（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S7-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 generation config 的正式归属与使用规则。

目标是：

1. 明确 config 是什么
2. 明确 config 由谁设定
3. 明确不同链路是否允许不同 config
4. 避免运行中频繁覆盖和漂移

## 2. 正式结论

本任务最终结论如下：

1. generation config 指模型调用的底层生成参数
2. config 应在链路定义时就固定下来
3. 第一版不采用层层覆盖机制
4. 不同链路允许使用不同 config
5. 同一链路内部不应频繁改动 config

## 3. Config 的定义

本任务中的 generation config 指：

1. `temperature`
2. `top_p`
3. `max_tokens`
4. `response_format`
5. `json_mode` 或结构化输出开关
6. `stop`
7. 其他 provider 底层生成参数

它回答的问题是：

`这次模型如何生成`

而不是：

`这次模型应该做什么`

后者属于 prompt。

## 4. Config 的归属

本任务明确规定：

1. config 的归属在模型调用上层
2. provider 只接收 config
3. provider 不拥有 config policy

也就是说：

1. provider 不决定该用什么 temperature
2. provider 不决定是否开启结构化输出
3. provider 只执行已经给定的 config

## 5. 不采用覆盖链

第一版明确不采用：

1. provider default
2. phase override
3. task override
4. step override

这种层层覆盖机制。

原因是：

1. 它会让 config 漂移
2. 会增加运行时不确定性
3. 很难追踪某次调用到底为何使用某组参数

## 6. 推荐策略

第一版建议采用：

1. 按链路预先定义 config
2. 在链路建立时固定下来
3. 在运行过程中不再频繁改动

也就是说：

1. 同一链路有一套固定 config
2. 不同链路可以有不同 config

## 7. 按链路区分

第一版允许以下链路拥有不同 config：

1. `prepare`
2. `execute`
3. `finalize`
4. `compression`
5. `final verification`
6. `memory recall`
7. `preference recall`
8. `subagent execution`

这样做的原因是：

1. 不同链路的生成目标不同
2. 不同链路对稳定性、结构化、成本的要求不同

## 8. Prompt 与 Config 的边界

本任务明确规定：

1. prompt 负责语义约束
2. config 负责生成控制

例如：

### 属于 prompt

1. 当前 phase 允许做什么
2. 当前输出应满足什么结构语义
3. 当前 agent 应如何决策

### 属于 config

1. `temperature`
2. `max_tokens`
3. `response_format`
4. `stop`

## 9. Response Format 的归属

本任务明确规定：

1. `response_format` 属于 generation config
2. 不属于 prompt 层

原因是：

1. 它是底层输出控制参数
2. 不是语义层行为约束

因此：

1. prompt 可以要求“输出结构化结果”
2. 但真正的格式开关归 config 控制

## 10. 与当前主链路的关系

基于当前架构，第一版建议理解为：

1. `execute` 使用固定 execute config
2. `finalize` 使用固定 finalize config
3. final verification 使用固定 verifier config
4. recall 链路使用固定 recall config

也就是说：

1. config 按链路分
2. 不按 run 内瞬时状态频繁变

## 11. 与 Provider 的关系

本任务与 `S7-T3` 对齐如下：

1. provider 接收 `generation_config`
2. provider 不解释 config policy
3. provider 不决定是否覆盖 config

provider 的职责只是：

1. 正确执行给定 config
2. 返回标准模型结果

## 12. 第一版边界

第一版明确不建议：

1. 在 step 内频繁改 temperature
2. 在 finalize 中动态重写 verifier config
3. 让 runtime 在运行中不断叠加覆盖层
4. 把 provider 特有参数泄漏成 runtime 核心策略

## 13. 对其他任务的直接输入

`S7-T4` 直接服务：

1. `S7-T5` budget / context control
2. `S7-T6` model adapter skeleton
3. `S1-T5` prompt assembly
4. `S11-T6` finalize pipeline

同时它直接依赖：

1. `S7-T2` 模型调用挂载结构
2. `S7-T3` model provider 边界

## 14. 本任务结论摘要

可以压缩成 5 句话：

1. generation config 是模型调用底层生成参数集合
2. config 应在链路定义时固定下来
3. 第一版不采用层层覆盖机制
4. 不同链路允许有不同 config
5. `response_format` 属于 config，不属于 prompt
