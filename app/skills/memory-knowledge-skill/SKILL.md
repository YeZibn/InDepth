---
name: memory-knowledge-skill
description: "Unified system memory skill: runtime candidate capture + structured memory_card governance in SQLite."
---

# Memory Knowledge Skill (V2)

## Overview

This skill is now fully aligned with the system-memory architecture:

1. Structured memory card storage (`memory_card`)
2. Runtime forced finalization at task end
3. Stage-triggered observability and evaluation

Legacy markdown memory files are no longer part of this skill.

## Primary Entry

```bash
python app/skills/memory-knowledge-skill/scripts/memory_card_cli.py --help
```

## Core Operations

### 0) Capture runtime candidate memory

Use tool `capture_runtime_memory_candidate` during execution when a reusable pattern emerges.

Required fields:
- `task_id`, `run_id`
- `title`
- `observation`

Optional fields:
- `proposed_action`
- `stage` (`pull_request` / `pre_release` / `postmortem` / etc.)
- `tags` (comma-separated)

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

## Runtime Integration

- Runtime injects memory recall at task start (LLM title-based, up to 5 cards, light inject: `memory_id + recall_hint`).
- Runtime forces task-end memory finalization in framework.
- This skill captures candidate memories during execution via explicit tool call `capture_runtime_memory_candidate`.
- Runtime supports full card retrieval by id via `get_memory_card_by_id`.
- Trigger/retrieval/decision events are persisted for KPI tracking.
