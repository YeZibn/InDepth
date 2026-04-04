# Memory Knowledge File Organization

## Directory Structure

```
# Skill bundle (this directory)
app/skills/memory-knowledge-skill/
├── assets/templates/            # Source templates used by scripts
│   ├── experience_template.md
│   └── principle_template.md
│
# Runtime data (generated under project root)
memory-knowledge/
├── experience/              # Experience records (lessons learned)
│   ├── INDEX.md            # Auto-generated index
│   └── YYYY-MM-DD-title.md # Individual experience files
│
├── principle/              # Principle records (rules to follow)
│   ├── INDEX.md            # Auto-generated index
│   └── category-title.md   # Individual principle files
```

## Experience Files

### Naming Convention
```
{YYYY-MM-DD}-{sanitized-title}.md
```

**Examples:**
- `2024-04-02-async-database-timeout.md`
- `2024-03-15-memory-leak-debugging.md`

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | string | Yes | Always "experience" |
| date | string | Yes | Date in YYYY-MM-DD format |
| category | string | Yes | One of: coding, debugging, architecture, performance, communication, workflow |
| tags | list | No | List of relevant tags |

### Categories

- **coding** - Code implementation lessons
- **debugging** - Problem diagnosis and resolution
- **architecture** - System design decisions
- **performance** - Optimization experiences
- **communication** - Collaboration insights
- **workflow** - Process improvements

## Principle Files

### Naming Convention
```
{category}-{sanitized-title}.md
```

**Examples:**
- `security-input-validation.md`
- `architecture-microservices.md`

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | string | Yes | Always "principle" |
| category | string | Yes | One of: coding-style, architecture, security, performance, workflow, testing |
| priority | string | Yes | One of: high, medium, low |
| created | string | Yes | Date in YYYY-MM-DD format |

### Categories

- **coding-style** - Code formatting and style guidelines
- **architecture** - System design principles
- **security** - Security best practices
- **performance** - Performance guidelines
- **workflow** - Development process rules
- **testing** - Testing standards

## INDEX.md Format

The INDEX.md files are auto-generated and should not be manually edited. They provide:

1. Total count of entries
2. Last updated timestamp
3. Grouped listing by category
4. Links to individual files

## File Templates

Source templates are maintained in:
- `app/skills/memory-knowledge-skill/assets/templates/experience_template.md`
- `app/skills/memory-knowledge-skill/assets/templates/principle_template.md`

### Experience Template

```markdown
---
type: experience
date: YYYY-MM-DD
category: [category]
tags: [tag1, tag2]
---

# Title

## Background
Context and situation

## Investigation
Steps taken

## Solution
What was done

## Outcome
Results

## Key Takeaway
Main lesson

## Related
- Task: 
- Code: 
```

### Principle Template

```markdown
---
type: principle
category: [category]
priority: [high|medium|low]
created: YYYY-MM-DD
---

# Title

## Definition
Clear statement

## Rationale
Why it matters

## Application
How to apply

## Exceptions
When not to apply

## References
Links and resources
```

## Best Practices

1. **Use consistent naming** - Follow the naming conventions strictly
2. **Fill all frontmatter** - Complete metadata helps with organization
3. **Write descriptive titles** - Should convey the essence at a glance
4. **Use appropriate categories** - Helps with browsing and filtering
5. **Tag liberally** - Makes content discoverable through search
6. **Link related items** - Connect experiences to tasks and code
7. **Keep INDEX updated** - Run update scripts after adding entries
