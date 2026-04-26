# S7-T3 Model Provider 边界（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S7-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 model provider 的正式职责边界。

目标是：

1. 明确 provider 负责什么、不负责什么
2. 切开 provider 与 runtime policy
3. 让主链路、final verification、prompt-build 共用同一套 provider 协议

## 2. 正式结论

本任务最终结论如下：

1. provider 只负责请求模型并返回标准结果
2. provider 不负责 prompt 组装
3. provider 允许处理技术性重试、超时和底层容错
4. provider 不负责语义性 fallback
5. provider 返回统一 model result，不夹带 runtime 判断
6. final verification 复用同一套 provider 接口

## 3. Provider 的职责

第一版 provider 的职责只包括：

1. 接收已经准备好的模型请求
2. 调用底层模型服务
3. 处理底层协议差异
4. 处理技术性超时与短重试
5. 返回统一结构化结果

## 4. Provider 不负责什么

第一版明确规定，provider 不负责：

1. prompt 组装
2. `RunContext` 解释
3. `StepResult` 生成
4. phase 判断
5. handoff 判定
6. graph 推进判断

也就是说：

1. provider 不知道 `RunContext`
2. provider 不知道 `TaskGraphState`
3. provider 不知道 `handoff`
4. provider 只知道一次模型调用请求

## 5. Prompt 组装边界

本任务明确规定：

1. prompt assembly 属于上层
2. provider 只接收已经准备好的输入

因此：

1. `base prompt`
2. `phase prompt`
3. `dynamic injection`
4. `handoff`

这些内容如何组合，不属于 provider 责任。

## 6. 技术性重试与语义性 fallback

本任务明确区分两类容错：

## 6.1 技术性重试

第一版允许 provider 处理：

1. 短暂网络失败
2. 瞬时服务不可用
3. 超时重试

这些都属于 provider 基础设施职责。

## 6.2 语义性 fallback

本任务明确规定：

1. “换一个模型重跑”
2. “降级到另一个模型角色”
3. “改策略再试一次”

这些都不属于 provider。

它们属于：

1. runtime policy
2. orchestration 层
3. 后续的 model routing / budget policy

## 7. Provider 返回结构

本任务建议 provider 统一返回标准 model result。

第一版至少应包含：

```ts
type ModelResult = {
  output_text?: string;
  structured_output?: unknown;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
  };
  finish_reason?: string;
  raw_response_ref?: string;
};
```

## 8. 返回结构的边界

本任务明确规定：

1. provider 返回模型结果
2. 不返回 runtime 级判断

因此不应由 provider 返回：

1. `next_phase`
2. `node_action`
3. `result_status`
4. `should_finalize`

这些都属于上层解释结果后的语义。

## 9. 与 final verification 的关系

本任务明确规定：

1. final verification 复用同一套 provider 协议
2. 不额外定义一套 verifier provider

区别只在于：

1. 调用位置不同
2. prompt 输入不同
3. 输出解释逻辑不同

但 provider 层仍然统一。

## 10. 推荐最小接口方向

第一版推荐 provider 接口方向如下：

```ts
interface ModelProvider {
  generate(request: ModelRequest): ModelResult;
}
```

其中：

```ts
type ModelRequest = {
  model_name: string;
  input: unknown;
  generation_config?: unknown;
};
```

这个接口的重点不是字段最终长什么样，而是边界：

1. 输入是已准备好的调用请求
2. 输出是统一模型结果

## 11. 与其他任务的关系

本任务与其他结构对齐如下：

1. `S1`
   prompt assembly 在 provider 之外
2. `S3`
   orchestration 不进入 provider
3. `S11`
   final verification 复用同一 provider
4. `S7-T4`
   generation config 的归属在 provider 外层再细化
5. `S7-T5`
   budget control 在 provider 外层再细化

## 12. 第一版边界

第一版明确不建议：

1. provider 直接读取 `RunContext`
2. provider 自己拼 prompt
3. provider 决定换模型策略
4. provider 决定业务层 fallback
5. 为 verifier 单独造第二套 provider 协议

## 13. 对其他任务的直接输入

`S7-T3` 直接服务：

1. `S7-T4` generation config 归属规则
2. `S7-T5` budget control 方案
3. `S7-T6` model adapter skeleton
4. `S11-T7` verification skeleton

同时它直接依赖：

1. `S7-T1` 模型调用场景清单
2. `S7-T2` 模型调用挂载结构

## 14. 本任务结论摘要

可以压缩成 5 句话：

1. provider 只负责请求模型并返回标准结果
2. provider 不负责 prompt 组装和 runtime 语义判断
3. provider 允许技术性重试，但不负责语义性 fallback
4. final verification 复用同一套 provider 接口
5. 上层负责解释模型结果并把它接入主链路
