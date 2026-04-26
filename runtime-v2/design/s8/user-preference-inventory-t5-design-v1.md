# S8-T5 User Preference 链路清单（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T5`

## 1. 当前主要文件

1. `app/core/memory/user_preference_store.py`
2. `app/core/runtime/user_preference_lifecycle.py`
3. `app/config/runtime_config.py`

## 2. 当前职责

当前 user preference 主要承载：

1. 偏好 recall
2. 偏好 extract
3. 偏好 capture / write

## 3. 当前主要入口

从现有代码看，user preference 有两条主线：

1. run 前 recall 注入
2. run 后 capture / write

## 4. 当前触发时机

目前主要触发点包括：

1. 主链路开始前，根据 `user_input` 注入 preference recall block
2. run closeout 后，基于 `user_input` 做 preference extract 和 write

## 5. 当前数据形态

当前主要数据形态包括：

1. recall block
2. LLM extract updates
3. preference store key/value

## 6. 与 v2 当前主干的关系

按目前已经收敛的 v2 设计，user preference 应理解为：

1. recall 属于 `dynamic injection`
2. extract / save 不再视为模型角色
3. extract / save 属于 finalize closeout 后置保存动作

## 7. 当前问题

当前最主要的问题有 4 个：

1. recall 与 capture 的触发仍写在 runtime lifecycle 中
2. extract 仍直接绑定当前 runtime model provider
3. recall block 直接插入消息链
4. preference save 还没有完全切到统一 handoff 视角

## 8. 与当前新设计的直接冲突点

当前最需要改造的点包括：

1. preference recall 应继续保留在 prompt build
2. preference extract / save 应迁移到 finalize 后置保存工具
3. write 动作不应再进入主链路 prompt

## 9. 对后续的直接输入

这份清单直接服务：

1. `S8-T6` user preference 定位、更新机制和注入规则
2. `S8-T7` memory hooks 设计
3. `S1-T4` prompt 与状态边界延伸

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. user preference 当前由 recall 和 capture 两条链路组成
2. recall 发生在 run 前，capture/write 发生在 run 后
3. 它当前仍与 runtime lifecycle 和当前 model provider 耦合
4. v2 中 recall 应继续归 dynamic injection
5. extract / save 应迁移到 finalize 后置保存动作
