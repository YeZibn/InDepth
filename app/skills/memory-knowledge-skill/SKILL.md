---
name: memory-knowledge-skill
description: "Manages long-term memory by saving experiences and principles to Markdown files. Invoke when encountering important lessons, best practices, coding patterns, or rules that should be remembered for future reference."
---

# Memory Knowledge Skill

## Overview

The Memory Knowledge Skill enables systematic capture and retrieval of valuable insights gained during software engineering work. It maintains two types of memory:

1. **Experience** - Lessons learned from actual practice (successes, failures, discoveries)
2. **Principle** - Guidelines and rules to follow (best practices, constraints, standards)

**When to use this skill:**
- After solving a difficult problem worth remembering
- When discovering a useful pattern or technique
- When establishing coding standards or conventions
- When encountering pitfalls to avoid in the future
- When refining workflows based on experience

## Quick Start

Run the commands below from the repository root (the directory containing `app/` and `memory-knowledge/`).

```bash
# Add a new experience
python app/skills/memory-knowledge-skill/scripts/add_experience.py "Fixed memory leak in async handler" \
  --category debugging \
  --tags "python,async,memory" \
  --content "The issue was caused by..."

# Add a new principle
python app/skills/memory-knowledge-skill/scripts/add_principle.py "Never block the UI thread" \
  --category architecture \
  --priority high \
  --content "Always offload heavy work..."

# Search memories
python app/skills/memory-knowledge-skill/scripts/search_memory.py "async"

# List all memories
python app/skills/memory-knowledge-skill/scripts/list_memories.py
```

## Memory Types

### Experience (经验)

Real-world lessons learned from practice. Each experience captures:
- **What happened** - The situation or problem
- **What was done** - The approach taken
- **Outcome** - Results and consequences
- **Key takeaway** - The lesson to remember

**Categories:**
- `coding` - Code implementation lessons
- `debugging` - Problem diagnosis and resolution
- `architecture` - System design decisions
- `performance` - Optimization experiences
- `communication` - Collaboration insights
- `workflow` - Process improvements

### Principle (原则)

Rules and guidelines to follow. Each principle defines:
- **What** - The rule or guideline
- **Why** - Rationale and reasoning
- **When** - Applicable scenarios
- **How** - Implementation guidance

**Categories:**
- `coding-style` - Code formatting and style
- `architecture` - System design principles
- `security` - Security best practices
- `performance` - Performance guidelines
- `workflow` - Development process rules
- `testing` - Testing standards

## Workflow

```
Encounter valuable insight
        ↓
Is it a lesson from practice?
    ├─ Yes → Create Experience
    │         - What was the situation?
    │         - What approach worked/failed?
    │         - What was learned?
    │
    └─ No → Create Principle
              - What rule should be followed?
              - Why is this important?
              - When does it apply?
        ↓
Save to memory-knowledge/
        ↓
Update INDEX.md
        ↓
Reference in future work
```

## Core Capabilities

### 1. Add Experience

Record a lesson learned from practice.

```bash
python app/skills/memory-knowledge-skill/scripts/add_experience.py <title> [options]

Options:
  --category    coding|debugging|architecture|performance|communication|workflow
  --tags        Comma-separated tags
  --content     Full content (or opens editor if not provided)
  --update      Update existing entry (exact date match, or title-only if unique)
```

**Example:**
```bash
python app/skills/memory-knowledge-skill/scripts/add_experience.py "Async database query timeout" \
  --category debugging \
  --tags "python,async,postgresql" \
  --content "Background: API was timing out under load...

Root cause: Connection pool exhaustion

Solution: Implemented connection pooling with asyncpg

Lesson: Always monitor connection pool usage in async apps"
```

### 2. Add Principle

Record a rule or guideline.

```bash
python app/skills/memory-knowledge-skill/scripts/add_principle.py <title> [options]

Options:
  --category    coding-style|architecture|security|performance|workflow|testing
  --priority    high|medium|low
  --content     Full content (or opens editor if not provided)
  --update      Update existing entry instead of failing on duplicates
```

**Example:**
```bash
python app/skills/memory-knowledge-skill/scripts/add_principle.py "Validate inputs at system boundaries" \
  --category security \
  --priority high \
  --content "Definition: All external inputs must be validated before processing

Rationale: Prevents injection attacks and data corruption

Application: API endpoints, file uploads, user inputs

Exceptions: Internal service-to-service calls with trusted data"
```

### 3. Search Memories

Find relevant memories by keyword.

```bash
python app/skills/memory-knowledge-skill/scripts/search_memory.py <query> [options]

Options:
  --type      experience|principle (filter by type)
  --category  Filter by category
```

**Example:**
```bash
# Search all memories for "async"
python app/skills/memory-knowledge-skill/scripts/search_memory.py async

# Search only experiences about debugging
python app/skills/memory-knowledge-skill/scripts/search_memory.py timeout --type experience --category debugging
```

### 4. List Memories

Browse all saved memories.

```bash
python app/skills/memory-knowledge-skill/scripts/list_memories.py [options]

Options:
  --type       experience|principle
  --category   Filter by category
  --sort       date|title|category (default: date)
```

**Example:**
```bash
# List all principles
python app/skills/memory-knowledge-skill/scripts/list_memories.py --type principle

# List recent experiences
python app/skills/memory-knowledge-skill/scripts/list_memories.py --type experience --sort date

# Update an existing principle's definition
python app/skills/memory-knowledge-skill/scripts/add_principle.py "Validate inputs at system boundaries" \
  --category security \
  --content "All external inputs must be validated at system boundaries..." \
  --update
```

## File Organization

```
# Skill bundle (this directory)
app/skills/memory-knowledge-skill/
├── assets/templates/              # Source templates used by scripts
│   ├── experience_template.md
│   └── principle_template.md
│
# Runtime data (generated by scripts)
memory-knowledge/
├── experience/                    # Experience records
│   ├── INDEX.md                  # Auto-generated index
│   └── YYYY-MM-DD-{title}.md     # Individual experiences
│
├── principle/                     # Principle records
│   ├── INDEX.md                  # Auto-generated index
│   └── {category}-{title}.md     # Individual principles
```

## File Formats

### Experience Format

```markdown
---
type: experience
date: 2024-04-02
category: debugging
tags: [python, async, memory]
---

# Async Database Query Timeout

## Background
API was experiencing timeouts under high load during peak hours.

## Investigation
1. Checked application logs - no errors
2. Monitored database - normal CPU/memory
3. Discovered connection pool was exhausted

## Solution
Implemented connection pooling with asyncpg and added pool size monitoring.

## Outcome
- Timeout rate dropped from 15% to 0.1%
- Response time improved by 40%

## Key Takeaway
Always monitor connection pool metrics in async applications. Default pool sizes are often insufficient for production load.

## Related
- Task: 20240401_143000_scale_api
- Code: src/db/pool.py
```

### Principle Format

```markdown
---
type: principle
category: security
priority: high
created: 2024-04-02
---

# Validate Inputs at System Boundaries

## Definition
All external inputs must be validated before processing, including:
- API request parameters
- File uploads
- User form submissions
- External service responses

## Rationale
Prevents:
- Injection attacks (SQL, command, XSS)
- Data corruption
- Unexpected application behavior
- Security vulnerabilities

## Application

### API Endpoints
```python
@app.post("/users")
async def create_user(data: UserCreate):
    # Validation happens via Pydantic model
    pass
```

### File Uploads
- Check file type against whitelist
- Verify file size limits
- Scan for malware if applicable

## Exceptions
- Internal service-to-service calls within trusted network
- Data from internal databases (already validated on entry)

## References
- OWASP Input Validation Cheat Sheet
- Company Security Guidelines
```

## Best Practices

### When to Create an Experience

✓ **Do create when:**
- Spent significant time (>30 min) solving a problem
- Discovered a non-obvious solution
- Learned something surprising
- Want to remember the approach for similar situations

✗ **Don't create when:**
- It's a simple, obvious solution
- It's already well-documented elsewhere
- It's a one-time issue unlikely to recur

### When to Create a Principle

✓ **Do create when:**
- Establishing team conventions
- Defining coding standards
- Documenting architectural decisions
- Setting security requirements

✗ **Don't create when:**
- It's personal preference without clear benefit
- It conflicts with existing principles
- It's too specific to one project

### Writing Quality Memories

1. **Be Specific**: Include concrete examples, not just abstract concepts
2. **Explain Why**: The reasoning is often more valuable than the rule itself
3. **Link Related Items**: Connect to tasks, code, documentation
4. **Use Tags**: Make memories discoverable through multiple keywords
5. **Keep Updated**: Revise principles as practices evolve

## Resources

### scripts/
- `add_experience.py` - Create new experience records
- `add_principle.py` - Create new principle records
- `search_memory.py` - Search across all memories
- `list_memories.py` - Browse and filter memories
- `utils.py` - Shared utilities (path resolution, etc.)

### references/
- `experience-template.md` - Writing guide for experience entries
- `principle-template.md` - Writing guide for principle entries
- `file-organization.md` - Detailed file structure guide

### assets/templates/
- `experience_template.md` - Source template loaded by `add_experience.py`
- `principle_template.md` - Source template loaded by `add_principle.py`

## Example Usage Flow

**Scenario:** After debugging a tricky race condition

```bash
# 1. Create an experience record
python app/skills/memory-knowledge-skill/scripts/add_experience.py "Race condition in cache invalidation" \
  --category debugging \
  --tags "concurrency,cache,race-condition" \
  --content "## Problem
Cache was returning stale data under high concurrency.

## Root Cause
Read and invalidate operations were not atomic.

## Solution
Used Redis Lua script for atomic check-and-delete.

## Lesson
Always consider atomicity when multiple operations touch shared state."

# 2. Derive a principle
python app/skills/memory-knowledge-skill/scripts/add_principle.py "Use atomic operations for cache invalidation" \
  --category architecture \
  --priority high \
  --content "## Definition
Cache invalidation must be atomic with respect to reads.

## Rationale
Prevents race conditions where stale data is returned.

## Implementation
- Use Redis Lua scripts for atomic operations
- Or use cache tags for bulk invalidation
- Never separate read-check from delete"

# 3. Search later when needed
python app/skills/memory-knowledge-skill/scripts/search_memory.py "cache race"
```
