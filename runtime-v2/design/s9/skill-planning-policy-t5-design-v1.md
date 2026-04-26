# S9-T5 Skill 参与主链路的规则（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 skill 是否参与 planning / prepare，以及在各 phase 中如何生效。

本任务不再讨论：

1. skill 生命周期
2. skill manifest 字段
3. subagent 与 skill 的关系

这里只回答三件事：

1. skill 是否参与所有 phase
2. skill 是否拥有独立 planning 权
3. 各 phase 如何获取 skill resource

## 2. 正式结论

第一版正式结论如下：

1. skill 参与所有 phase
2. skill 不拥有独立 planning 权
3. 各 phase 默认只看到轻量 skill prompt
4. 任何 phase 要获取 skill resource，都必须通过 tool

## 3. Skill 在各 Phase 中的地位

第一版明确规定：

1. `prepare` 可见 skill
2. `execute` 可见 skill
3. `finalize` 可见 skill

原因是：

1. skill 属于当前 agent 的能力面
2. 能力面不应只在某一阶段存在

## 4. Skill 不拥有独立 Planning 权

第一版明确不引入：

1. skill planner
2. 由 skill 单独决定 graph
3. 由 skill 单独决定 phase 切换

也就是说：

1. skill 可以影响主链路判断
2. 但 skill 不成为独立决策者

## 5. Skill 的默认生效方式

第一版 skill 在所有 phase 中的默认生效方式只有两种：

1. 轻量 prompt 注入
2. 按需 resource access

本任务明确规定：

1. capability layer 中只放轻量 skill prompt
2. skill 正文和附属资源不默认注入 prompt

## 6. `prepare` 阶段

`prepare` 可以利用 skill，但方式仍然受统一约束。

允许：

1. 读取 capability layer 中的 skill 轻量提示
2. 基于 skill 能力面辅助建立初始主线

不允许：

1. 让 skill 接管 planning
2. 默认直接拿到 skill 正文资源

## 7. `execute` 阶段

`execute` 是第一版 skill 最主要的发挥阶段。

允许：

1. 读取 capability layer 中的 skill 轻量提示
2. 在需要时通过 tool 读取 skill resource

结论：

1. skill 的详细资源使用通常发生在 execute
2. 但仍然必须走正式 tool 入口

## 8. `finalize` 阶段

`finalize` 也可以看到 skill，但它只作为能力背景存在。

允许：

1. 读取 capability layer 中的 skill 轻量提示
2. 在需要时通过 tool 读取 skill resource

不允许：

1. 把 skill 变成额外 closeout 子系统

## 9. Skill Resource 的获取规则

第一版正式规定：

1. 不管是 `prepare / execute / finalize`
2. 任何 phase 要获取 skill resource
3. 都必须通过 tool

这里的 skill resource 包括：

1. instructions
2. references
3. scripts

这意味着：

1. phase 不因自己所处阶段不同而拥有特殊读取特权
2. resource 读取规则在所有 phase 中统一

## 10. 为什么这样收

第一版采用这套规则的原因如下：

1. 保持 skill 的能力面角色稳定
2. 避免把 skill 重新做成独立 planning 子系统
3. 让 resource access 规则在所有 phase 中统一
4. 保持 prompt 注入轻量化

## 11. 对后续任务的直接输入

`S9-T5` 直接服务：

1. `S9-T6` 生命周期管理
2. `S1` capability layer 的 skill 注入边界
3. `S6` skill resource access tool 的治理方式
4. `S3` 各 phase 中对 skill 的统一使用方式

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. skill 参与所有 phase
2. skill 不拥有独立 planning 权
3. 各 phase 默认只看到轻量 skill prompt
4. skill resource 不默认注入 prompt
5. 任何 phase 获取 skill resource 都必须通过 tool
