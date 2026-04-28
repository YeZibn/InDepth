# S1-T5 Prompt Assembly 机制（V1）

更新时间：2026-04-28  
状态：Draft  
对应任务：`S1-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 prompt assembly 的正式机制。

本任务不再讨论：

1. prompt 有哪些资产
2. prompt 与状态边界的总规则
3. recall 的触发时机

这里只回答三件事：

1. prompt 在 runtime 中按哪些层组装
2. 各层分别放什么
3. assembler 最终输出什么

## 2. 正式结论

第一版 prompt assembly 顶层固定为三层：

1. `base prompt`
2. `phase prompt`
3. `dynamic injection`

并明确规定：

1. `PromptAssembler` 内部按这三层装配
2. 第一版正式输出保持三段 prompt block 结构
3. 不强制在 prompt 模块内先收口成 `system_prompt + user_prompt`

## 3. 三层结构

## 3.1 `base prompt`

`base prompt` 是稳定底座。

允许放：

1. 系统角色
2. runtime 总原则
3. 长期行为约束
4. 通用安全边界
5. 稳定写作/执行准则

不放：

1. 当前 phase
2. 当前 task
3. 当前 recall 结果
4. 当前 node 的运行时事实

## 3.2 `phase prompt`

`phase prompt` 是当前阶段专属规则层。

允许放：

1. `prepare / execute / finalize` 当前阶段规则
2. 当前阶段的输出格式要求
3. 当前阶段允许/禁止的动作
4. 当前阶段专属 contract

本任务明确规定：

1. output contract 不单独拉一层
2. phase 输出约束直接归入 `phase prompt`
3. 模块 16 第一版先重点服务 `execute`
4. `prepare / finalize` 先保留接口，不要求同轮落完

## 3.3 `dynamic injection`

`dynamic injection` 用于承载当前这次运行时才确定的动态上下文。

允许放：

1. 当前 `user_input`
2. 当前 `goal`
3. 当前 `active_node` / task 信息
4. 当前 node 相关的局部图上下文
5. `runtime memory` 注入文本
6. 当前 agent 可用的 tool capability 摘要
7. `finalize_return_input`
8. 当前必须面对的显式任务约束

不放：

1. 稳定长期协议
2. 当前 phase 规则正文
3. 没有边界的“其他本轮临时事实”兜底块

补充规定：

1. `runtime memory` 注入是第一版固定组成项，不作为可有可无的挂件
2. `tool capability` 采用轻量摘要文本进入 prompt
3. 原始 tool schema 继续走模型/tool calling 通道，不在这里展开为大段 prompt 文本
4. 已有上下文中的最近观察或 `reflexion hint` 如需进入 prompt，应作为 `runtime memory` 或 node 局部上下文的一部分被提取，而不是再单独扩一层

## 4. 层与层的关系

第一版采用固定顺序叠加：

1. `base prompt`
2. `phase prompt`
3. `dynamic injection`

这表示：

1. 越往后越具体
2. 后层可以补充前层
3. 后层不能推翻前层正式规则

例如：

1. `dynamic injection` 不能推翻 `phase prompt`
2. `dynamic injection` 不能推翻 `base prompt`
3. `phase prompt` 不能推翻 `base prompt`

## 5. 必选层与可空层

第一版建议如下：

1. `base prompt`：必选
2. `phase prompt`：必选
3. `dynamic injection`：必选

补充说明：

1. `dynamic injection` 是必选，但其内部某些子项可空
2. 第一版中 `runtime memory` 注入作为正式输入项保留，即使为空也应有稳定装配位
3. execute 阶段通常会完整使用三层
4. `prepare / finalize` 后续按各自需要细化其注入项

## 6. `PromptAssembler` 的定位

`PromptAssembler` 的职责不是自由拼 prompt，而是按固定三层顺序组装当前模型可见输入。

因此它负责：

1. 读取各层输入
2. 组装层级结构
3. 产出稳定的 prompt block 结构

它不负责：

1. 决定 recall 是否触发
2. 决定 graph 如何推进
3. 决定 tool 如何执行
4. 决定 memory 如何检索
5. 决定 node 如何调度

## 7. 输出形态

第一版明确规定：

1. `PromptAssembler` 内部可使用分层结构对象
2. 对外先输出正式三段 prompt block 结构
3. 是否进一步渲染为某个具体模型调用所需的 message 形态，由上层调用方决定

也就是说：

1. 内部先形成可检查的 prompt blocks
2. 三段 block 是当前模块的正式边界
3. 具体模型适配层后续可以再把它们渲染成文本或消息

## 8. 为什么这样设计

采用这套机制的原因如下：

1. 所有真正进入模型输入的内容都被纳入 prompt 定义
2. 顶层组成与 `S1-T2` 的正式分层保持一致
3. `current node`、`runtime memory`、`tool capability` 都被收敛进 `dynamic injection`
4. output contract 不再悬空，而是跟 `phase prompt` 绑定
5. 中间态仍然可检查、可调试
6. 避免 prompt 模块内部又膨胀出第二套自定义层体系

## 9. 对后续任务的直接输入

`S1-T5` 直接服务：

1. `S1-T6` prompt 迁移方案
2. 模块 16 的接口定义与 assembler 骨架实现
3. `S8` recall / preference / runtime memory 注入挂点
4. `S11` finalize prompt 与 handoff 输出约束

## 10. 本任务结论摘要

可以压缩成 6 句话：

1. 第一版 prompt assembly 顶层固定为三层
2. 三层分别是 `base prompt / phase prompt / dynamic injection`
3. `current node`、`runtime memory`、`tool capability` 都归 `dynamic injection`
4. output contract 跟随 `phase prompt`
5. assembler 只负责装配，不负责 recall、tool 执行和 graph 推进
6. 第一版先输出三段 prompt block 结构
