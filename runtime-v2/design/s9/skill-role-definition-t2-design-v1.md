# S9-T2 Skill 正式角色定义（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 skill 的正式角色。

本任务不再讨论：

1. 当前有哪些 skill
2. subagent 如何设计
3. tool 协议细节

这里只回答三件事：

1. skill 在 v2 中到底是什么
2. skill prompt 应该承担什么角色
3. skill 与 tool / resources 的边界是什么

## 2. 正式结论

第一版正式结论如下：

1. `skill` 是能力包
2. `skill prompt` 只承担轻量 `when to use` 角色
3. `skill prompt` 从 `SKILL.md` frontmatter 派生
4. `SKILL.md` frontmatter 先只保留 `name` 和 `description`
5. `skill body / references / scripts` 不默认注入 prompt
6. `skill` 可以提供 tool，但 tool 仍归统一 tool 系统治理

## 3. Skill 的正式角色

第一版中，`skill` 的正式角色是：

1. 能力说明包
2. 资源打包单元
3. 可选 tool 暴露单元

这意味着：

1. skill 不是单纯 prompt 片段
2. skill 也不是单纯工具集合
3. skill 是 agent 当前能力面的一个正式单元

## 4. Skill Prompt 的角色

第一版中，`skill prompt` 只承担一个轻量角色：

1. 告诉模型什么时候应当使用这个 skill

因此它的定位是：

1. `when to use`
2. 触发条件提示
3. 适用边界提示

而不是：

1. 方法正文
2. 长篇教程
3. 资源全文注入

## 5. Frontmatter 规则

第一版 `SKILL.md` frontmatter 先只保留两个正式字段：

1. `name`
2. `description`

其中：

1. `name` 用于稳定标识 skill
2. `description` 用于生成轻量 skill prompt

## 5.1 `description` 的写法

第一版建议 `description` 采用简短 `when to use` 风格。

要求如下：

1. 控制字数
2. 重点写触发场景
3. 重点写适用问题
4. 不写方法细节

## 6. Skill Prompt 的生成方式

第一版中，skill prompt 的生成方式为：

1. 从 frontmatter 读取 `name`
2. 从 frontmatter 读取 `description`
3. 生成轻量能力提示文本

这部分内容在 v2 中进入：

1. `capability layer`

## 7. Skill 正文与资源的地位

第一版明确规定：

1. `SKILL.md` 正文不默认注入 capability layer
2. `references` 不默认注入 capability layer
3. `scripts` 不默认注入 capability layer

这些内容的定位是：

1. 按需读取的 skill 资源
2. 用于执行过程中的补充能力支持

## 8. Skill 与 Tool 的边界

第一版明确规定：

1. skill 自身可以提供 tool
2. 但这些 tool 仍属于统一 tool 系统的一部分

也就是说：

1. skill 负责打包和描述能力
2. tool 负责正式执行接口

因此 skill 与 tool 的关系应理解为：

1. `skill` 可以带 tool
2. `tool` 不因此脱离统一 tool 系统治理

## 9. Skill 在 Prompt Assembly 中的位置

第一版正式规定：

1. 当前 agent 开启的 skill 提示进入 `capability layer`

这里进入的是：

1. frontmatter 派生出的轻量提示

不是：

1. 完整 `SKILL.md`
2. references 正文
3. scripts 正文

## 10. 对后续任务的直接输入

`S9-T2` 直接服务：

1. `S9-T3` skill manifest
2. `S9-T4` skill 与 prompt/tool/resource/dependency 关系
3. `S1` capability layer 的进一步细化
4. `S6` tool system 与 skill tool 暴露对齐

## 11. 本任务结论摘要

可以压缩成 6 句话：

1. `skill` 在 v2 中是能力包
2. `skill prompt` 只负责轻量 `when to use`
3. `SKILL.md` frontmatter 先只保留 `name + description`
4. `description` 采用简短触发式写法
5. `SKILL.md` 正文、references、scripts 都不默认注入 prompt
6. skill 可以带 tool，但 tool 仍归统一 tool 系统治理
