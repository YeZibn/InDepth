# InDepth

一个基于 Agno 框架的智能 Agent 系统，支持记忆管理、任务跟踪和 Skill 开发。

## 项目结构

```
InDepth/
├── InDepth.md                    # Agent 行为准则
├── app/
│   ├── agent/                    # Agent 实现
│   │   ├── agent.py              # 基础 Agent
│   │   ├── create_skill_agent.py # Skill 创建 Agent
│   │   └── memory_agent.py        # 记忆 Agent
│   ├── skills/                   # Skills
│   │   ├── memory-knowledge-skill/  # 记忆管理
│   │   ├── skill-creator/         # Skill 创建框架
│   │   └── todo-skill/            # 任务跟踪
│   └── tool/                      # 工具集
├── memory_knowledge/              # 知识库
│   └── base/
│       ├── experience/            # 经验沉淀
│       └── principles/            # 原则沉淀
├── todo/                          # 任务跟踪
└── db/                            # 数据库
```

## 核心功能

### 1. Agent 系统

| Agent | 说明 |
|-------|------|
| `BaseAgent` | 基础 Agent，加载 InDepth.md 行为准则 |
| `CreateSkillAgent` | 专门用于创建和打包 Skill |
| `MemoryAgent` | 记忆管理 Agent |

### 2. 记忆系统 (memory_knowledge)

Agent 自主管理长期知识，包括：
- **经验 (experience)**: Bug修复、踩坑记录
- **原则 (principles)**: 最佳实践、规则规范

### 3. 任务跟踪 (todo-skill)

复杂任务自动创建 Todo，支持：
- 步骤分解
- 依赖关系
- 进度跟踪
- 阻塞状态

### 4. Skill 框架 (skill-creator)

标准化 Skill 开发流程：
1. 理解需求
2. 规划资源
3. 初始化
4. 编辑
5. 打包
6. 迭代

## 快速开始

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 2. 运行 Agent

```bash
python app/agent/agent.py
```

### 3. 创建 Skill

```bash
python app/agent/create_skill_agent.py
```

## 行为准则

Agent 遵循 `InDepth.md` 中的准则：

- **先确认，后执行**: 信息不全不动手
- **先检索，后行动**: 遇到问题先查记忆库
- **自主管理**: 记忆和 Todo 由 Agent 自动维护
- **适度原则**: 避免无限循环

## 技术栈

- **Agno**: Agent 框架
- **DashScope**: 阿里云模型服务
- **SQLite**: 历史记录存储
