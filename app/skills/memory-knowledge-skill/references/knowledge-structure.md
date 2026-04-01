# 知识库结构说明

## 目录结构

```
memory_knowledge/
├── base/
│   ├── experience/              # 经验和重要场景
│   │   ├── INDEX.md              # 经验索引
│   │   └── YYYY-MM-DD-*.md       # 经验文档
│   └── principles/              # 规则和指南
│       ├── INDEX.md              # 原则索引
│       └── rule-name.md          # 原则文档
```

## 知识类型

| 类型 | 说明 | 存放位置 | 命名规则 |
|------|------|----------|----------|
| **Experience** | 事件、场景、问题、洞见 | `experience/` | `YYYY-MM-DD-简短标题.md` |
| **Principle** | 规则、指南、最佳实践 | `principles/` | `规则名称.md` |

## Experience vs Principle

### Experience（范围更广）

经验文档记录**任何重要事件或洞见**：

- **问题解决**：修复的 bug、解决的问题、找到的变通方案
- **重要场景**：边界情况、意外行为、关键场景
- **决策记录**：做出的重要选择及其原因
- **发现**：有用的发现、模式、优化方法
- **经验教训**：什么有效、什么无效、为什么发生

**核心原则**：如果未来可能有用，就记录下来。

### Principle（可复用规则）

原则文档记录**通用指南**：

- **应该/不应该**：要做什么或避免什么
- **最佳实践**：验证过的方法和模式
- **约束条件**：技术或业务限制
- **标准规范**：编码规范、架构决策

## 索引文件格式

每个知识类型都有 `INDEX.md`：

```markdown
# Experience/Principles 索引

> 自动生成，新增文档时更新此文件

| 文件 | 描述 | 标签 |
|------|------|------|
| [filename.md](filename.md) | 简短描述（≤30字） | #tag1 #tag2 |
```

## 示例

### Experience 示例

| 场景 | 文件名 |
|------|--------|
| 修复数据库超时 | `2026-03-31-db-connection-timeout.md` |
| 发现 API 限流行为 | `2026-03-31-api-rate-limit-behavior.md` |
| 选择架构模式 | `2026-03-31-microservices-decision.md` |
| 遇到异步竞态条件 | `2026-03-31-async-race-condition.md` |

### Principle 示例

| 规则 | 文件名 |
|------|--------|
| UI 线程禁止阻塞 IO | `no-blocking-io-on-ui-thread.md` |
| 始终验证用户输入 | `validate-user-input.md` |
| 使用连接池 | `use-connection-pooling.md` |
