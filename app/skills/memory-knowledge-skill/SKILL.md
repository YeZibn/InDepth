---
name: memory-knowledge-skill
description: Agent 长时经验记忆模块。触发条件：遇到问题需要查经验、完成重要工作需要沉淀、主动检索相关知识。
allowed-tools:
  - "execute_bash_command"
  - "read_file"
  - "write_file"
metadata:
  version: "5.0.0"
  author: "InDepth"
---

# Memory Knowledge 操作指南

## 知识库位置

所有记忆知识存储在：`memory_knowledge/`

```
memory_knowledge/
├── base/
│   ├── experience/              # 经验知识目录
│   │   ├── INDEX.md              # 经验索引
│   │   └── *.md                  # 经验文档
│   └── principles/              # 原则知识目录
│       ├── INDEX.md              # 原则索引
│       └── *.md                  # 原则文档
```

## 何时触发

智能体应**自主判断**以下场景，无需用户提示：

| 场景 | 动作 | 触发条件 |
|------|------|---------|
| 遇到问题 | 先搜索 memory_knowledge | 错误信息、不确定解决方案 |
| 完成重要工作 | 主动沉淀知识 | bug修复、踩坑、新功能 |
| 做决策前 | 查看行为准则 | 涉及规范、安全、架构 |

## 知识类型

| 类型 | 判断标准 | 存放位置 | 文件命名 |
|------|---------|---------|---------|
| experience | 发生了什么、怎么解决的 | `memory_knowledge/base/experience/` | `YYYY-MM-DD-简短标题.md` |
| principle | 应该/不应该做什么、为什么 | `memory_knowledge/base/principles/` | `规则名称.md` |

---

## 检索流程

智能体应**自主执行**以下检索流程：

```
遇到问题
    ↓
1. 查看索引文件，快速定位相关知识
   read_file memory_knowledge/base/experience/INDEX.md
   read_file memory_knowledge/base/principles/INDEX.md
    ↓
2. 搜索关键词（如索引不够详细）
   execute_bash_command: rg "关键词" memory_knowledge/base/experience/
   execute_bash_command: rg "关键词" memory_knowledge/base/principles/
    ↓
3. 读取完整内容
   read_file memory_knowledge/base/experience/YYYY-MM-DD-xxx.md
    ↓
4. 融入上下文，参考历史解决方案
```

---

## 沉淀流程

智能体完成重要工作后，应**自主判断**并执行沉淀：

```
完成重要工作
    ↓
1. 判断知识类型
   - 有具体解决过程、踩坑经历 → experience
   - 有通用规则、行为准则 → principle
    ↓
2. 使用下方模板创建文档
   - experience: memory_knowledge/base/experience/YYYY-MM-DD-标题.md
   - principle: memory_knowledge/base/principles/规则名称.md
    ↓
3. 更新索引文件（必须）
   在 INDEX.md 中添加新条目：文件名 + 简短描述 + 标签
```

---

## 索引文件

位置：`memory_knowledge/base/experience/INDEX.md` 或 `memory_knowledge/base/principles/INDEX.md`

```markdown
# Experience/Principles 索引

| 文件 | 描述 | 标签 |
|------|------|------|
| [filename.md](filename.md) | 一句话概括 | #标签1 #标签2 |
```

**要求**：
- 描述不超过 30 字
- 标签从文档提取，便于检索

---

## Experience 模板

**位置**：`memory_knowledge/base/experience/TEMPLATE.md`

```markdown
# [简短标题]

> 文件命名：YYYY-MM-DD-简短标题.md

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

**位置**：`memory_knowledge/base/principles/TEMPLATE.md`

```markdown
# [规则名称]

> 文件命名：rule-name.md（如 no-blocking-io-on-ui-thread.md）

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

## 工具调用速查

```bash
# 查看经验索引
read_file memory_knowledge/base/experience/INDEX.md

# 查看原则索引
read_file memory_knowledge/base/principles/INDEX.md

# 搜索经验
execute_bash_command: rg "关键词" memory_knowledge/base/experience/

# 搜索原则
execute_bash_command: rg "关键词" memory_knowledge/base/principles/

# 按标签搜索
execute_bash_command: rg "#bug" memory_knowledge/base/experience/
```

---

## 智能体行为准则

- **自主触发**：无需用户提示，自主判断何时检索/沉淀
- **搜索即停**：获得有效信息后立即停止
- **标签准确**：便于后续检索
- **必须索引**：新增知识后必须更新 INDEX.md
- **路径明确**：所有路径使用完整相对路径
