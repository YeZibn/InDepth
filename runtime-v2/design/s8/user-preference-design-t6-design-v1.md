# S8-T6 User Preference 定位与更新规则（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 user preference 的正式定位与更新规则。

目标是：

1. 明确 user preference 层在 `S8` 中的职责
2. 明确 recall 时机与方式
3. 明确 write 输入来源与更新方式
4. 明确 user preference 与长期记忆层的边界

## 2. 正式结论

本任务最终结论如下：

1. user preference 只保存 user-specific preference
2. user preference 第一版完全以 `md` 为主
3. recall 只在 run 最开始发生一次
4. recall 直接整页注入 prompt
5. write 通过 `handoff.preference_payload` 驱动
6. write 采用按 key 更新 md 的方式

## 3. User Preference 的定位

user preference 在 v1 中的定位是：

1. 保存用户长期稳定的协作偏好
2. 为整次 run 提供用户偏好背景

它不负责：

1. 保存一般性长期知识
2. 保存当前 run 的运行期上下文
3. 保存项目级长期事实

## 4. 第一版偏好范围

第一版最小偏好范围包括：

1. `language_preference`
2. `response_style`
3. `format_preference`
4. `tooling_preference`
5. `goal_preference`

## 5. 存储方式

本任务明确规定：

1. user preference 第一版以 `md` 为主
2. 第一版不补 sqlite 辅助检索层

这样做的原因是：

1. 用户偏好更适合人工查看和维护
2. 用户偏好不需要 system memory 那样的轻召回检索层

## 6. Recall 规则

第一版 user preference recall 规则如下：

1. 只在整次 run 最开始触发一次
2. 不按 phase 重复 recall
3. 不按 step 重复 recall
4. recall 直接把整份偏好 md 注入 prompt
5. 不做筛选
6. 不做 matcher

这意味着：

1. user preference 作为整次 run 的共享偏好背景
2. 后续所有 phase 共用这份初始注入

## 7. Write 输入来源

本任务明确规定：

1. user preference write 通过 `handoff.preference_payload` 驱动
2. 必要时可参考原始 `user_input`
3. 但正式 closeout 输入主位是 `handoff`

第一版结构如下：

```ts
type PreferencePayload = {
  candidates: Array<{
    preference_key:
      | "language_preference"
      | "response_style"
      | "format_preference"
      | "tooling_preference"
      | "goal_preference";
    value: string;
    summary: string;
  }>;
};
```

## 8. Write 时机

本任务明确规定：

1. user preference write 发生在 finalize closeout 后
2. 不在 execute 中途写
3. 不在 run 中频繁增量写

## 9. Write 行为方式

本任务明确规定：

1. 第一版不采用整页重写
2. 第一版采用按 key 更新 md 中对应段落的方式

也就是说：

1. `language_preference` 更新 `language_preference` 对应段
2. `response_style` 更新 `response_style` 对应段
3. 其余 key 同理

这样做的好处是：

1. 更新更稳定
2. 更适合长期维护
3. 更不容易破坏整份偏好文档结构

## 10. 与主链路的关系

user preference 与主链路的关系如下：

1. recall 挂在 run-start / prompt-build
2. write 挂在 finalize-closeout
3. recall 进入 prompt
4. write 不进入当前主判定链

## 11. 与长期记忆层的边界

本任务再次明确：

1. user preference 保存的是用户偏好
2. 长期记忆层保存的是长期知识、经验、事实、模式、背景

也就是说：

1. 用户偏好层不保存一般性知识
2. 长期记忆层不保存 user-specific preference

## 12. 对其他任务的直接输入

`S8-T6` 直接服务：

1. `S8-T7` memory domain 总设计
2. `S11-T3` handoff 字段扩展
3. `S11-T6` finalize memory hooks
4. `S1-T4` prompt / state / recall 边界

同时它直接依赖：

1. `S8-T5` user preference 现状清单
2. `S8-T7` memory domain 重设计

## 13. 本任务结论摘要

可以压缩成 5 句话：

1. user preference 只保存 user-specific preference
2. 第一版完全以 `md` 为主，不补 sqlite
3. recall 在 run 开始时整页注入，不做筛选
4. write 通过 `handoff.preference_payload` 驱动
5. write 采用按 key 更新 md 的方式
