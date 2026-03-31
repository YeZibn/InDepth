---
name: memory-knowledge
description: Agent 长时经验记忆模块。触发条件：遇到问题需要查经验、完成重要工作需要沉淀、主动检索相关知识。
allowed-tools:
  - "execute_bash_command"
  - "read_file"
  - "write_file"
metadata:
  version: "4.0.0"
  author: "InDepth"
---

# Memory Knowledge 操作指南

## 何时触发

| 场景 | 动作 |
|------|------|
| 遇到问题 | 先搜索 memory_knowledge 是否有相关经验 |
| 完成重要工作 | bug修复、踩坑、新功能实现 → 主动沉淀 |
| 需要行为准则 | 决策前查看是否有相关原则 |

## 知识类型

| 类型 | 判断标准 | 存放位置 | 文件命名 |
|------|---------|---------|---------|
| experience | 发生了什么、怎么解决的 | `base/experience/` | `YYYY-MM-DD-title.md` |
| principle | 应该/不应该做什么、为什么 | `base/principles/` | `rule-name.md` |

---

## 检索流程

```
遇到问题
    ↓
1. 查看索引文件，快速定位相关知识
   read_file memory_knowledge/base/experience/INDEX.md
   read_file memory_knowledge/base/principles/INDEX.md
    ↓
2. 搜索关键词（如索引不够详细）
   rg "关键词" memory_knowledge/base/experience/
   rg "关键词" memory_knowledge/base/principles/
    ↓
3. 读取完整内容
   read_file memory_knowledge/base/experience/YYYY-MM-DD-xxx.md
    ↓
4. 融入上下文，参考历史解决方案
```

---

## 沉淀流程

```
完成重要工作
    ↓
1. 判断知识类型
   - 有具体解决过程、踩坑经历 → experience
   - 有通用规则、行为准则 → principle
    ↓
2. 写入对应目录
   experience: memory_knowledge/base/experience/YYYY-MM-DD-title.md
   principle:  memory_knowledge/base/principles/rule-name.md
    ↓
3. 使用模板（见下方）
    ↓
4. 更新索引文件（必须）
   在 INDEX.md 中添加新条目：文件名 + 简短描述 + 标签
```

---

## 索引文件

每个目录都有 `INDEX.md`，格式如下：

```markdown
# Experience/Principles 索引

> 自动生成，每次新增后更新此文件

| 文件 | 描述 | 标签 |
|------|------|------|
| [filename.md](filename.md) | 简短描述（一句话概括内容） | #标签1 #标签2 |
```

**索引条目要求**：
- 描述：一句话概括，不超过 30 字
- 标签：从文档中提取关键标签

---

## Experience 模板

**文件命名**：`YYYY-MM-DD-简短标题.md`（如 `2026-03-30-textual-async-loading.md`）

```markdown
# [简短标题]

## 问题
描述遇到的问题或场景，包括：
- 问题的具体表现
- 触发条件
- 相关的错误信息（如有）

## 解决过程
1. 尝试方案1（失败原因）
2. 尝试方案2（失败原因）
3. 最终方案（成功）

## 结果
- 最终解决方案是什么
- 关键收获或教训
- 后续注意事项

## 标签
#bug #fix #组件名 #技术栈
```

---

## Principle 模板

**文件命名**：`rule-name.md`（如 `no-blocking-io-on-ui-thread.md`）

```markdown
# [规则名称]

## 规则
如果 [条件]，则 [行为]

## 原因
为什么这条规则是这样的：
- 技术原因
- 业务原因
- 历史教训

## 示例
- 正确做法：...
- 错误做法：...

## 标签
#规范 #安全 #性能
```

---

## 搜索命令速查

```bash
# 查看索引（推荐第一步）
read_file memory_knowledge/base/experience/INDEX.md
read_file memory_knowledge/base/principles/INDEX.md

# 搜索所有经验
rg "关键词" memory_knowledge/base/experience/

# 搜索所有原则
rg "关键词" memory_knowledge/base/principles/

# 按标签搜索
rg "#bug" memory_knowledge/base/experience/
rg "#安全" memory_knowledge/base/principles/
```

---

## 注意事项

- **搜索足够即停**：获得有效信息后立即停止搜索
- **不要重复搜索**：已获取的信息不要重复搜索
- **标签要准确**：使用常见标签便于后续检索
- **标题要简洁**：能一眼看出内容主题
- **必须更新索引**：新增知识后必须更新对应的 INDEX.md
