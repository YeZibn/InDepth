# S8-T3 System Memory 链路清单（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T3`

## 1. 当前主要文件

1. `app/core/memory/system_memory_store.py`
2. `app/core/memory/recall_service.py`
3. `app/core/runtime/system_memory_lifecycle.py`
4. `app/tool/runtime_memory_harvest_tool.py`

## 2. 当前职责

当前 system memory 主要承载：

1. 经验卡存储
2. recall query 构建
3. recall block 渲染
4. task 结束后的 memory finalize

## 3. 当前主要入口

从现有代码看，system memory 有两个主要入口：

1. run 开始前的 recall 注入
2. run 结束后的 finalize 写入

## 4. 当前触发时机

目前主要触发点包括：

1. 主链路开始前，根据 `user_input` 做 recall
2. run closeout 时，根据 handoff / memory seed 做写入

## 5. 当前数据来源

当前 system memory 的主要输入包括：

1. `user_input`
2. recall query
3. memory card store
4. task 结束时的 `verification_handoff` / `memory_seed`

## 6. 与 v2 当前主干的关系

按目前已经收敛的 v2 设计，system memory 应理解为：

1. recall 属于 `prompt-build -> dynamic injection`
2. write 属于 finalize closeout 后置保存动作
3. 它不应再直接挂在主链路决策中心

## 7. 当前问题

当前最主要的问题有 4 个：

1. recall 触发时机写在 runtime lifecycle 中
2. finalize 写入仍绑定旧的 `verification_handoff`
3. recall block 直接改写 messages
4. system memory policy 和 runtime closeout 仍然耦合

## 8. 与当前新设计的直接冲突点

当前最需要改造的点包括：

1. 旧 `verification_handoff` 应切换到统一 `handoff`
2. finalize write 应迁移到 post-closeout memory hook
3. recall 结果应继续留在 dynamic injection，而不是进入 `RunContext`

## 9. 对后续的直接输入

这份清单直接服务：

1. `S8-T4` system memory 正式定位与 recall 机制
2. `S8-T7` memory hooks 设计
3. `S11-T6` finalize memory hooks 对接

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. system memory 当前有 recall 和 finalize write 两条主链路
2. recall 发生在 run 开始前，write 发生在 run 结束后
3. 它当前仍与 runtime lifecycle 和旧 handoff 语义耦合
4. v2 中 recall 应继续归 prompt build，write 应归 finalize 后置 hook
5. 下一步核心是把旧 `verification_handoff` 切换到统一 `handoff`
