---
name: memory-knowledge-skill
description: |
  Long-term memory system for agents to store, retrieve, and manage experiential knowledge and principles.
  Use when: (1) encountering problems that may have historical solutions (2) experiencing important scenarios worth recording (3) completing significant work that warrants preservation (4) making decisions that need principled guidance (5) user requests knowledge management operations.
metadata:
  version: "6.1.0"
  author: "InDepth"
---

# Memory Knowledge

A persistent knowledge management system that enables agents to learn from experience and apply accumulated wisdom to future tasks.

## Knowledge Base Location

```
memory_knowledge/
├── base/
│   ├── experience/              # Experiences and important scenarios
│   │   ├── INDEX.md
│   │   └── YYYY-MM-DD-*.md
│   └── principles/              # Behavioral rules and guidelines
│       ├── INDEX.md
│       └── rule-name.md
```

## Knowledge Types

| Type | Purpose | Location | Naming |
|------|---------|----------|--------|
| **Experience** | Record experiences, scenarios, problems, and insights | `experience/` | `YYYY-MM-DD-brief-title.md` |
| **Principle** | Capture reusable rules and guidelines | `principles/` | `rule-name.md` |

### Experience vs Principle

**Experience** captures:
- Problem-solving processes and solutions
- Important scenarios encountered (successes, failures, edge cases)
- Key decisions and their outcomes
- Unexpected behaviors or discoveries
- Lessons learned from any significant event

**Principle** captures:
- General rules about what should/shouldn't be done
- Best practices and their rationale
- Architectural decisions and constraints
- Behavioral guidelines

---

## Retrieval Workflow

**Trigger**: When facing a problem or decision, proactively search for relevant knowledge.

```
Step 1: Check indexes for quick navigation
        → read_file memory_knowledge/base/experience/INDEX.md
        → read_file memory_knowledge/base/principles/INDEX.md

Step 2: Search by keyword if needed
        → rg "keyword" memory_knowledge/base/experience/
        → rg "keyword" memory_knowledge/base/principles/

Step 3: Read full content
        → read_file memory_knowledge/base/experience/YYYY-MM-DD-xxx.md

Step 4: Apply findings and STOP searching
```

**Important**: Stop immediately once useful information is found. Avoid redundant searches.

---

## Knowledge Preservation Workflow

**Trigger**: Proactively preserve knowledge after significant events.

### When to Preserve

| Scenario | Type | Examples |
|----------|------|----------|
| Solved a difficult problem | Experience | Bug fixes, debugging sessions, workarounds |
| Encountered important scenario | Experience | Edge cases, unexpected behaviors, critical decisions |
| Learned something valuable | Experience | New insights, gotchas, better approaches |
| Discovered a reusable pattern | Principle | Best practices, architectural rules, coding standards |
| Identified a rule to follow | Principle | Security guidelines, performance rules, conventions |

### Decision Flow

```
Significant event occurred
    ↓
Is this a specific event/scenario/insight?
    ├─ Yes → Create Experience document
    └─ No → Is this a reusable rule/guideline?
              ├─ Yes → Create Principle document
              └─ No → No preservation needed
    ↓
Update INDEX.md (REQUIRED)
```

### Document Creation

Use scripts for consistent formatting:

```bash
# Create experience document
python scripts/add_experience.py "Title" \
  --scenario "Scenario description" \
  --insight "Key insight or solution" \
  --tags "tag1,tag2"

# Alternative: use --problem/--solution for problem-solving records
python scripts/add_experience.py "Bug fix title" \
  --problem "Problem description" \
  --solution "Solution steps" \
  --tags "bug,fix"

# Create principle document
python scripts/add_principle.py "rule-name" \
  --rule "If [condition], then [behavior]" \
  --reason "Why this rule exists" \
  --tags "tag1,tag2"
```

Or create manually following templates in `references/`.

### Index Update Requirement

**Every new document MUST update the corresponding INDEX.md:**

```markdown
| [filename.md](filename.md) | Brief description (≤30 chars) | #tag1 #tag2 |
```

---

## Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `init_knowledge.py` | Initialize knowledge base structure | `python scripts/init_knowledge.py [--path PATH]` |
| `add_experience.py` | Create experience document + update index | `python scripts/add_experience.py "title" [options]` |
| `add_principle.py` | Create principle document + update index | `python scripts/add_principle.py "name" [options]` |
| `search_knowledge.py` | Search knowledge base | `python scripts/search_knowledge.py "keyword" [options]` |

---

## Templates

Detailed templates available in `references/`:

- **Experience**: `references/experience-template.md`
- **Principle**: `references/principle-template.md`
- **Structure Guide**: `references/knowledge-structure.md`

---

## Behavioral Guidelines

| Guideline | Description |
|-----------|-------------|
| **Proactive** | Retrieve and preserve knowledge without user prompting |
| **Stop when found** | Cease searching once useful information is obtained |
| **Always index** | Update INDEX.md after creating any document |
| **Accurate tags** | Use lowercase, consistent tags for better retrieval |
| **Concise descriptions** | Keep index entries under 30 characters |
| **Capture value** | Record any experience with potential future value |
