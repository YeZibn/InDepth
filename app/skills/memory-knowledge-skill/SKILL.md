---
name: memory-knowledge-skill
description: "Lightweight system memory skill: govern memory_card data, inspect recall results, and manage the simplified SQLite schema."
---

# Memory Knowledge Skill

## Overview

This skill is aligned with the current V1 memory architecture:

1. `memory_card` is the only long-lived system memory card table
2. Formal memory is persisted only after task end
3. The persistence source is `verification_handoff.memory_seed`
4. Runtime default memory access is read-only recall plus fetch-by-id

This skill is mainly for governance, inspection, and offline maintenance of system memory data.

## Primary Entry

```bash
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py --help
```

## Core Operations

### 1) Upsert a card from JSON

```bash
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  upsert-json app/skills/memory-knowledge-skill/references/memory_card.example.json
```

### 2) Search cards

```bash
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  search "retry idempotency" --limit 5
```

### 3) List due-review cards

```bash
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py \
  due --days 7 --limit 50
```

## Data Layout

- `db/system_memory.db`
  - `memory_card`
  - `memory_trigger_event`
  - `memory_retrieval_event`
  - `memory_decision_event`

## Current Card Schema

`memory_card` only keeps lightweight fields:

1. `id`
2. `title`
3. `recall_hint`
4. `content`
5. `status`
6. `updated_at`
7. `expire_at`

## Runtime Integration

- Runtime performs start-of-run memory recall injection
- Recall is lightweight by default: inject `memory_id + recall_hint`
- If a recalled card becomes important, Runtime can fetch the full card with `get_memory_card_by_id`
- Runtime finalization is explicitly split into `finalizing(answer)` and `finalizing(handoff)`
- Formal memory persistence happens only after `finalizing(handoff)`
- Persistence reads only `verification_handoff.memory_seed`
- Trigger, retrieval, and decision events are persisted for observability

## Important Notes

- Runtime candidate memory is no longer the default mainline path
- This skill should not describe runtime-time candidate capture as the recommended architecture
- Vector retrieval is not part of the current V1 implementation
