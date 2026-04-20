# Memory Knowledge Skill

This skill manages the current lightweight system memory design.

## Core Commands

```bash
# Show help
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py --help

# Upsert one memory card from JSON
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  upsert-json app/skills/memory-knowledge-skill/references/memory_card.example.json

# Search memory cards
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  search "idempotency retry" --limit 5

# List due-review cards
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  due --days 7 --limit 50
```

## Storage

- SQLite DB: `db/system_memory.db`
- Main table: `memory_card`
- Event tables: `memory_trigger_event`, `memory_retrieval_event`, `memory_decision_event`

## Current Rules

- Formal memory persistence happens only after task end
- Persistence source is `verification_handoff.memory_seed`
- Runtime default memory tools are `search_memory_cards` and `get_memory_card_by_id`
- Recall is lightweight by default: `memory_id + recall_hint`
- `memory_card` uses the simplified schema:
  - `id`
  - `title`
  - `recall_hint`
  - `content`
  - `status`
  - `updated_at`
  - `expire_at`

## Notes

- Legacy markdown-based memory workflow has been removed
- Runtime candidate memory is not the recommended default path anymore
- Event tables are still retained for KPI tracking and postmortem analysis
