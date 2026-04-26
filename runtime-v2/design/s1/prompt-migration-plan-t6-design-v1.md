# S1-T6 Prompt 迁移方案（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S1-T6`

## 1. 目标

本任务用于定义现有 prompt 资产如何迁移到 `runtime-v2` 已确定的六层 prompt assembly 结构中。

本任务不再发明新的 prompt 层，而是回答：

1. 旧 prompt 资产有哪些来源
2. 它们分别迁到哪一层
3. 迁移时应遵守什么顺序

## 2. 正式结论

现有 prompt 资产按六层结构迁移：

1. `base layer`
2. `phase layer`
3. `task layer`
4. `capability layer`
5. `memory layer`
6. `context layer`

第一版迁移策略采用：

1. 先做来源盘点
2. 再做层级归位
3. 最后做旧 prompt 清退

## 3. 旧 Prompt 资产来源

第一版至少识别以下 7 类旧资产来源：

1. 系统级 instructions
2. `InDepth.md`
3. phase prompts
4. skill prompt
5. tool descriptions
6. memory / preference recall
7. messages / compression

## 4. 迁移映射

## 4.1 `base layer`

迁入：

1. 系统级 instructions
2. `InDepth.md`
3. 长期稳定的系统规则

作用：

1. 形成稳定底座
2. 承接原本长期常驻的系统说明

## 4.2 `phase layer`

迁入：

1. `PREPARING_PHASE_PROMPT`
2. `EXECUTING_PHASE_PROMPT`
3. `FINALIZING_PHASE_PROMPT`
4. 各 phase 对应的输出约束

作用：

1. 让阶段规则不再散落在 runtime 主类中
2. 统一收进阶段层

## 4.3 `task layer`

迁入：

1. 当前 `user_input`
2. 当前 `goal`
3. task graph 摘要
4. active node 摘要
5. `finalize_return_input`
6. 当前任务级显式约束

作用：

1. 表达这次 run 当前正在推进什么

## 4.4 `capability layer`

迁入：

1. 当前 agent 开启的 skill 描述
2. 当前 agent 可用的 tool 描述

作用：

1. 表达当前 agent 的真实能力面
2. 让 skill / tool 描述不再散落在系统 prompt 各处

## 4.5 `memory layer`

迁入：

1. system memory recall
2. user preference

作用：

1. 承接启动时一次性召回的长期背景

## 4.6 `context layer`

迁入：

1. messages
2. compression 之后的上下文内容
3. 必要的近期执行摘要
4. 执行期 fetch 到的补充材料

作用：

1. 承接当前模型调用前已经形成的上下文材料

## 5. 迁移中的关键规则

第一版明确规定：

1. 不允许把旧 prompt 大块原文整段照搬进新结构而不分层
2. phase 规则必须从 runtime 主类中拆出，进入 `phase layer`
3. skill / tool 描述必须进入 `capability layer`
4. recall 结果必须进入 `memory layer`
5. messages / compression 必须进入 `context layer`

## 6. 推荐迁移顺序

第一版建议按以下顺序迁移：

1. 先迁 `base layer`
2. 再迁 `phase layer`
3. 再迁 `capability layer`
4. 再迁 `task / memory / context` 三类运行期动态层
5. 最后清退旧 runtime 中散落的 prompt 拼接逻辑

## 7. 迁移完成后的目标形态

迁移完成后，旧 prompt 资产应形成以下稳定形态：

1. 长期规则进入 `base`
2. 阶段规则进入 `phase`
3. 当前任务锚点进入 `task`
4. agent 能力面进入 `capability`
5. recall 进入 `memory`
6. messages / compression 进入 `context`

## 8. 对后续任务的直接输入

`S1-T6` 直接服务：

1. `S3-T6` runtime skeleton 中的 prompt 装配入口
2. `S8` recall 注入落位
3. `S9` skills 与 capability layer 的对接
4. `S10` subagent prompt 能力面表达

## 9. 本任务结论摘要

可以压缩成 6 句话：

1. 现有 prompt 资产至少分 7 类来源
2. 它们统一迁入六层 prompt assembly 结构
3. 系统 instructions 和 `InDepth.md` 进入 `base`
4. phase prompts 进入 `phase`
5. 当前 agent 开启的 `skills / tools` 进入 `capability`
6. messages / compression 最终进入 `context`
