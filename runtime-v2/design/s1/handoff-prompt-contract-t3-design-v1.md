# S1-T3 Handoff Prompt Contract（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S1-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 `handoff` 与 prompt 层的正式契约。

目标是：

1. 明确 `handoff` 在 prompt 体系中的位置
2. 明确哪些链路允许消费 `handoff`
3. 避免 `handoff` 重新污染普通 `execute` prompt

## 2. 正式结论

本任务最终结论如下：

1. `handoff` 只属于 `finalize / final verification / RunOutcome` 链路
2. `handoff` 不进入普通 `execute` 主 prompt
3. final verification 直接消费统一 `handoff`
4. verification fail 回退 `execute` 时，只回灌 `finalize_return_input`
5. `handoff` 在 prompt 层不作为常驻 dynamic injection

## 3. Handoff 在 Prompt 体系中的位置

按当前 prompt 分层，`handoff` 不属于：

1. `base prompt`
2. `dynamic injection`
3. 普通 `execute phase prompt`

`handoff` 的正式位置是：

1. `finalize phase prompt` 的输出契约
2. final verification 的正式输入
3. `RunOutcome` 的正式组成部分

## 4. Execute Prompt 与 Handoff 的边界

本任务明确规定：

1. 普通 `execute` step 不直接消费 `handoff`
2. `handoff` 不作为 execute 阶段常驻上下文输入
3. `execute` 不能把 `handoff` 当作长期运行摘要来反复使用

原因是：

1. `handoff` 是收尾阶段正式交接包
2. 它不应反向污染主执行链路
3. execute 应继续围绕当前 node 与局部图上下文工作

## 5. Finalize Prompt 与 Handoff 的关系

本任务明确规定：

1. `finalize` 负责生成统一 `handoff`
2. `handoff` 是 finalize 的正式产出之一
3. `finalize phase prompt` 必须约束 handoff 的结构化输出

也就是说：

1. `handoff` 在 prompt 层首先是 finalize 的输出 contract
2. 然后才是 verification 的输入

## 6. Final Verification 与 Handoff 的关系

本任务明确规定：

1. final verification 直接消费统一 `handoff`
2. verifier 不回头消费主链路完整上下文
3. verifier 不依赖 execute 消息历史

因此：

1. `handoff` 是 verifier 在 prompt 层最核心的输入载体
2. 它不是主链路动态上下文块

## 7. Verification Fail 回退时的规则

本任务明确规定：

1. verification fail 后，不把整份 `handoff` 回灌 `execute`
2. 回到 `execute` 时只注入 `finalize_return_input`

推荐结构如下：

```ts
type FinalizeReturnInput = {
  verification_summary: string;
  verification_issues: string[];
};
```

这意味着：

1. execute 只拿到返工所需问题
2. 不拿到完整 `handoff`

## 8. Prompt Contract 的正式含义

本任务所说的 `handoff prompt contract`，第一版主要包括两部分：

1. finalize 输出 handoff 的结构约束
2. verifier 消费 handoff 的输入约束

也就是说，它不是：

1. 一份新的 handoff 对象定义
2. 一份常驻主链路 prompt 片段

而是：

1. finalize 与 verification 之间共享的 prompt-level 契约

## 9. 对其他任务的直接输入

`S1-T3` 直接服务：

1. `S11-T3` 统一 handoff 结构
2. `S11-T4` finalize / verification / outcome 闭环
3. `S11-T6` finalize pipeline 规则
4. `S1-T5` prompt assembly 机制

同时它直接依赖：

1. `S1-T2` prompt 分层结构
2. `S11-T3` handoff 结构定义
3. `S4-T4` finalize_return_input 挂载

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. `handoff` 只属于 `finalize / verification / outcome` 链路
2. `handoff` 不进入普通 `execute` 主 prompt
3. finalize 负责生成 handoff，verifier 负责消费 handoff
4. verification fail 回到 `execute` 时只注入 `finalize_return_input`
5. `handoff` 不是主链路常驻 dynamic injection
