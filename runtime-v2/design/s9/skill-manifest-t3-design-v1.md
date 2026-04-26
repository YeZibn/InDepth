# S9-T3 Skill Manifest（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S9-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 skill 的最小 manifest。

本任务不再讨论：

1. skill 与 tool 的正式绑定关系
2. subagent 的 manifest
3. skill 生命周期管理细节

这里只回答三件事：

1. skill manifest 的作用是什么
2. 第一版最少包含哪些字段
3. 这些字段分别给谁消费

## 2. 正式结论

第一版 skill manifest 只保留最小结构：

```ts
type SkillManifest = {
  name: string;
  description: string;
  references: string[];
  scripts: string[];
};
```

并明确规定：

1. manifest 是 runtime 消费对象
2. 第一版不把 `tools` 提前放进 manifest
3. skill 与 tool 的绑定关系留给 `S9-T4` 讨论

## 3. Manifest 的作用

第一版中，manifest 的作用不是做重型描述层，而是做：

1. skill 的统一读取面
2. loader 的稳定输出
3. manager 的稳定输入
4. capability 注入与资源访问的标准来源

一句话说：

manifest 的作用是把“一个 skill 的正式可消费信息”标准化。

## 4. 最小字段定义

### 4.1 `name`

作用：

1. skill 的稳定标识

来源：

1. `SKILL.md` frontmatter

### 4.2 `description`

作用：

1. skill 的轻量 `when to use` 描述
2. capability layer 的直接来源

来源：

1. `SKILL.md` frontmatter

### 4.3 `references`

作用：

1. 列出该 skill 可按需读取的 reference 资源

来源：

1. skill 目录下 `references/` 资源索引

### 4.4 `scripts`

作用：

1. 列出该 skill 可按需读取或执行的脚本资源

来源：

1. skill 目录下 `scripts/` 资源索引

## 5. 字段消费方

| 字段 | 主要消费方 | 用途 |
|---|---|---|
| `name` | loader / manager / capability layer | 识别 skill |
| `description` | capability layer | 生成轻量 skill prompt |
| `references` | resource access 链路 | 按需读取参考资料 |
| `scripts` | resource/script access 链路 | 按需读取或执行脚本 |

## 6. 为什么不提前放 `tools`

第一版不把 `tools` 放进 manifest，原因如下：

1. tool 的正式归属在 `S6`
2. skill 与 tool 的绑定关系本身就是 `S9-T4` 的讨论重点
3. 现在提前写进 manifest，会把边界写死过早

因此：

1. manifest 先只描述 skill 自己的最小可消费信息
2. skill-tool 关系后续再正式接入

## 7. 为什么不再加更多字段

第一版不引入以下字段：

1. `version`
2. `author`
3. `tags`
4. `examples`
5. `dependencies`

原因如下：

1. 当前没有明确系统消费方
2. 先保持 manifest 极简
3. 等后续确有稳定需求再加

## 8. 对后续任务的直接输入

`S9-T3` 直接服务：

1. `S9-T4` skill 与 prompt/tool/resource/dependency 关系
2. `S9-T6` 生命周期管理
3. `S1` capability layer 的 skill 注入来源

## 9. 本任务结论摘要

可以压缩成 5 句话：

1. skill manifest 是 runtime 消费对象
2. 第一版 manifest 只保留 `name / description / references / scripts`
3. `name + description` 主要来自 frontmatter
4. `references / scripts` 主要来自 skill 目录资源索引
5. `tools` 暂不进入 manifest，留给 `S9-T4` 再讨论
