# Skills 实现说明

## 文档定位

本文记录 `runtime-v2` 当前 skill 模块的实际落地情况、代码入口、主链接线和当前边界。

它对应的是模块 17 的实现结果，不替代 `design/s9/` 下的设计稿。

## 当前代码入口

当前 skill 模块代码位于：

1. [models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/skills/models.py)
2. [loader.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/skills/loader.py)
3. [registry.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/skills/registry.py)
4. [tools.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/skills/tools.py)
5. [__init__.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/skills/__init__.py)

主链接线入口位于：

1. [runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)

## 当前正式结构

### 静态 manifest

当前 skill 的静态消费对象是：

1. `SkillManifest`

第一版字段包括：

1. `name`
2. `description`
3. `references`
4. `scripts`
5. `assets`

### 运行态对象

当前 skill 的运行态对象是：

1. `RuntimeSkill`

第一版字段包括：

1. `manifest`
2. `source_path`
3. `instructions`
4. `status`

### 最小状态

第一版 `SkillStatus` 包括：

1. `loaded`
2. `enabled`
3. `disabled`

## 当前加载与注册链路

当前最小链路如下：

1. host / orchestrator 显式提供 `skill_paths`
2. `LocalSkillLoader` 从本地目录加载 skill
3. loader 解析 `SKILL.md` frontmatter 与正文
4. loader 收集 `references / scripts / assets` 相对路径
5. `SkillRegistry` 持有 `RuntimeSkill`
6. 已加载 skill 在当前主链中默认会被 enable
7. skill resource access tools 会注册进统一 `ToolRegistry`

## 当前 Loader 规则

`LocalSkillLoader` 第一版支持：

1. 单个 skill 目录路径
2. 包含多个 skill 子目录的父目录路径

第一版硬规则：

1. `SKILL.md` 必须存在
2. frontmatter 必须至少有 `name + description`
3. `frontmatter.name == skill_folder_name`

第一版资源规则：

1. `references / scripts / assets` 保存为相对 skill 根目录的相对路径
2. 缺少这些目录时允许为空
3. `source_path` 保存 skill 根目录绝对路径

## 当前 Prompt 接线

当前 enabled skill 会以轻量 capability 摘要进入 prompt 主链。

规则如下：

1. 只有 `enabled` skill 进入 prompt
2. 只注入一行摘要：
   - `- <name>: <description>`
3. skill 摘要并入现有 capability 文本
4. 当前挂载到 prompt 的 `dynamic_injection`

不进入 prompt 的内容：

1. `SKILL.md` 正文
2. `references`
3. `scripts`
4. `assets`

## 当前 Tool 接线

当前已正式落地四个只读 skill resource access tools：

1. `get_skill_instructions`
2. `get_skill_reference`
3. `get_skill_script`
4. `get_skill_asset`

规则如下：

1. 全部走统一 `ToolRegistry`
2. 全部通过 `SkillRegistry` 找到 `RuntimeSkill`
3. 全部返回 JSON 字符串
4. `get_skill_script` 不执行脚本
5. `get_skill_asset` 第一版按文本读取

路径安全策略：

1. 请求路径必须在 manifest 已登记资源列表中
2. 最终目标路径必须仍位于 skill 根目录下

## 当前实现边界

已经完成：

1. 本地目录型 skill loader
2. 最小 runtime skill registry
3. enabled skill prompt 摘要注入
4. 四个只读 skill resource tools
5. skill_paths 到 orchestrator 的最小自动装载链

尚未完成：

1. host 层更正式的 skill 配置入口
2. skill dependency / version / reload
3. 二进制 asset 支持
4. skill marketplace / remote install
5. script 执行
6. subagent 与 skill 的深度联动

## 当前测试

当前已覆盖的测试包括：

1. [test_skills.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_skills.py)
2. [test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

主要覆盖：

1. skill loader 正常加载
2. frontmatter 缺失校验
3. 目录名一致校验
4. registry enable / disable
5. skill prompt 摘要注入
6. 四个只读 skill resource tools
