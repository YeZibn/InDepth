# Memory Knowledge Skill (V2)

This skill now uses **structured system memory cards** as the only source of truth.

## Core Commands

```bash
# Show help
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py --help

# Runtime capture (tool call inside runtime)
# capture_runtime_memory_candidate(task_id, run_id, title, observation, ...)

# Upsert one memory card from JSON
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  upsert-json app/skills/memory-knowledge-skill/references/memory_card.example.json

# Search memory cards
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  search "idempotency retry" --stage pull_request --limit 5

# List due-review cards
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  due --days 7 --limit 50
```

## Storage

- SQLite DB: `db/system_memory.db`
- Main table: `memory_card`
- Event tables: `memory_trigger_event`, `memory_retrieval_event`, `memory_decision_event`

## Notes

- Legacy markdown-based memory workflow has been removed.
- Runtime does not inject memory at task start.
- Runtime forces memory finalization at task end.
- Runtime candidate capture is part of this single skill (`capture_runtime_memory_candidate`).
