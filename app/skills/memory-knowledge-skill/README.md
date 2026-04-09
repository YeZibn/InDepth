# Memory Knowledge Skill

This skill captures and retrieves long-term engineering memory as Markdown files.

## What It Stores

1. `experience` - practice-based lessons learned
2. `principle` - reusable rules and standards

## Main Entry

Use the unified CLI:

```bash
python app/skills/memory-knowledge-skill/scripts/memory_cli.py --help
```

### Examples

```bash
# Add experience
python app/skills/memory-knowledge-skill/scripts/memory_cli.py add experience \
  "Async DB timeout root cause" \
  --category debugging \
  --tags "python,async,postgres" \
  --content "Connection pool was exhausted under burst traffic."

# Add principle
python app/skills/memory-knowledge-skill/scripts/memory_cli.py add principle \
  "Validate external input at boundaries" \
  --category security \
  --priority high \
  --content "All external input must be validated before processing."

# Search
python app/skills/memory-knowledge-skill/scripts/memory_cli.py search async --type experience

# List
python app/skills/memory-knowledge-skill/scripts/memory_cli.py list --type principle --sort category
```

## Legacy Scripts (Still Supported)

- `add_experience.py`
- `add_principle.py`
- `search_memory.py`
- `list_memories.py`

## Data Layout

Runtime files are written to:

- `memory-knowledge/experience/*.md`
- `memory-knowledge/principle/*.md`

Index files are auto-generated:

- `memory-knowledge/experience/INDEX.md`
- `memory-knowledge/principle/INDEX.md`
