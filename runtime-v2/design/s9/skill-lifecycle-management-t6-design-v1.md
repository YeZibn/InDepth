# S9-T6 Skill 生命周期管理（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 skill 的最小生命周期管理方式。

本任务不再讨论：

1. skill 版本管理
2. skill 与 subagent 的协作
3. 自动依赖安装

这里只回答三件事：

1. skill 生命周期有哪些正式状态
2. 各状态分别代表什么
3. enable / disable / deprecated 的边界是什么

## 2. 正式结论

第一版 skill 生命周期采用以下 5 个正式状态：

1. `discovered`
2. `loaded`
3. `enabled`
4. `disabled`
5. `deprecated`

并明确规定：

1. `disable` 是 agent 级停用
2. `deprecated` 仍允许历史读取
3. 第一版不单独设计 `reload`

## 3. 五个正式状态

## 3.1 `discovered`

表示：

1. 系统已经发现该 skill
2. 但还未形成正式运行期对象

## 3.2 `loaded`

表示：

1. skill 已被解析
2. frontmatter、references、scripts 等已进入统一读取对象

## 3.3 `enabled`

表示：

1. skill 已进入当前 agent 的能力面
2. capability layer 可以看到这个 skill 的轻量提示

## 3.4 `disabled`

表示：

1. skill 不再进入当前 agent 的 capability layer
2. 当前 agent 不再把它当成已启用能力

## 3.5 `deprecated`

表示：

1. skill 已不再作为当前有效 skill 使用
2. 但仍保留历史读取价值

## 4. 生命周期阶段说明

第一版可用下面这条主链路理解：

```text
discover -> load -> enable
                    -> disable
                    -> deprecated
```

## 5. `discover`

`discover` 的作用是：

1. 从指定路径中发现 skill
2. 确认该 skill 存在

这一阶段不要求：

1. 已完成解析
2. 已进入 capability layer

## 6. `load`

`load` 的作用是：

1. 解析 `SKILL.md`
2. 解析 frontmatter
3. 建立 references / scripts 索引
4. 形成 manifest / 运行期 skill 对象

这一阶段后，skill 已成为统一可消费对象，但还不一定已启用。

## 7. `enable`

`enable` 的作用是：

1. 把 skill 纳入当前 agent 的能力面
2. 使其轻量 skill prompt 进入 `capability layer`

第一版明确规定：

1. 只有 `enabled` skill 才进入当前 agent 的 capability layer

## 8. `disable`

第一版明确规定：

1. `disable` 是 agent 级停用

这意味着：

1. skill 只是从当前 agent 能力面拿掉
2. 不等于全系统删除
3. 不等于 skill 文件消失

## 9. `deprecated`

第一版明确规定：

1. `deprecated` 是比 `disabled` 更强的状态

含义是：

1. skill 不再作为当前有效 skill 使用
2. 但仍允许历史读取
3. 仍保留追溯与兼容价值

## 10. 为什么不单独做 `reload`

第一版不单独设计 `reload`，原因如下：

1. 当前生命周期先保持最小
2. `reload` 可以被视为组合动作
3. 没必要先把生命周期做重

第一版建议把 `reload` 理解为：

1. `disable`
2. `load`
3. `enable`

的组合行为，而不是独立正式状态。

## 11. 对后续任务的直接输入

`S9-T6` 直接服务：

1. skill manager 的最小运行模型
2. capability layer 对已启用 skill 的读取边界
3. 后续可能的 enable / disable 控制接口

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. 第一版 skill 生命周期采用 `discovered / loaded / enabled / disabled / deprecated`
2. `enable` 表示进入当前 agent 能力面
3. `disable` 只是 agent 级停用
4. `deprecated` 仍允许历史读取
5. 第一版不单独设计 `reload`
