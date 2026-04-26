# S9-T4 Skill 与 Prompt / Tool / Resource 的关系（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 skill 与 prompt、tool、resource 之间的正式关系。

本任务不再讨论：

1. dependency 系统
2. subagent 与 skill 的关系
3. skill 生命周期管理

这里只回答三件事：

1. skill 如何进入 prompt
2. skill 如何通过 tool 暴露资源访问能力
3. skill 自身资源如何归位

## 2. 正式结论

第一版 skill 只保留以下三类正式关系：

1. `skill -> prompt`
2. `skill -> tool`
3. `skill -> resource`

并明确规定：

1. 第一版不讨论 dependency
2. skill 不直接对外提供独立 capability tool
3. `skill -> tool` 只保留 resource access 语义

## 3. `skill -> prompt`

第一版中，skill 进入 prompt 的方式是轻注入。

它的正式规则如下：

1. skill 只把 frontmatter 派生出的轻量提示进入 prompt
2. 进入 prompt 的内容主要来自：
   - `name`
   - `description`
3. 这部分内容进入 `capability layer`

本任务明确规定：

1. `SKILL.md` 正文不默认进入 prompt
2. references 不默认进入 prompt
3. scripts 不默认进入 prompt

## 4. `skill -> tool`

第一版中，skill 与 tool 的关系被严格限制为：

1. resource access tool

也就是说：

1. skill 可以通过 tool 暴露自己的资源访问能力
2. 但 skill 不直接挂出独立 capability tool

## 4.1 允许的 tool 语义

第一版允许 skill 对外暴露的 tool 语义仅包括：

1. 读取 skill instructions
2. 读取 skill references
3. 读取或执行 skill scripts

它们的作用是：

1. 让 agent 在需要时读取 skill 资源
2. 让 skill 资源成为正式可访问对象

## 4.2 不允许的 tool 语义

第一版明确不允许：

1. skill 直接对外提供新的领域 capability tool

原因如下：

1. 这会让 skill 侧重新长出一套平行 tool 体系
2. 会削弱 `S6` 统一 tool 系统的边界
3. 会让 skill 的角色从能力包膨胀成执行系统

## 5. `skill -> resource`

第一版中，skill 自身资源包括：

1. `SKILL.md` 正文
2. references
3. scripts
4. assets

它们的正式定位是：

1. skill 的按需资源
2. skill 的能力支撑材料

它们默认：

1. 不进入 prompt
2. 不进入 state
3. 只在需要时通过 resource access tool 读取

## 6. 三类关系的总图

| 关系 | 第一版语义 | 是否默认进入 prompt |
|---|---|---|
| `skill -> prompt` | 轻量 frontmatter 注入 | 是 |
| `skill -> tool` | 只保留 resource access | 否 |
| `skill -> resource` | 按需资源 | 否 |

## 7. 为什么这样收

第一版采用这套关系的原因如下：

1. 保持 skill 边界稳定
2. 保持 tool 系统边界稳定
3. 保持 capability layer 轻量
4. 让 skill 资源通过正式访问方式暴露，而不是整段注入

## 8. 对后续任务的直接输入

`S9-T4` 直接服务：

1. `S9-T5` skill planning policy
2. `S9-T6` 生命周期管理
3. `S1` capability layer 的 skill 注入边界
4. `S6` tool system 与 skill resource access 对齐

## 9. 本任务结论摘要

可以压缩成 5 句话：

1. 第一版 skill 只保留 prompt、tool、resource 三类关系
2. `skill -> prompt` 是轻量 frontmatter 注入
3. `skill -> tool` 只保留 resource access 语义
4. `skill -> resource` 是按需资源关系
5. 第一版不讨论 dependency，也不允许 skill 挂独立 capability tool
