# Agent Integration for PPT Work

## Intent

Define lightweight contracts for systems where a main agent coordinates one or more subagents.

## Role Model

1. Main Agent
- Own planning, routing, checkpoints, and final synthesis.
- Decide output layer and review gates.

2. Research Subagent (optional)
- Collect and organize supporting facts.
- Return evidence with uncertainty notes.

3. Structure Subagent (optional)
- Build outline and section logic.
- Keep audience and purpose alignment.

4. Review Subagent (optional)
- Stress-test logic, evidence coverage, and narrative consistency.

## Routing Rule (Simple)

1. If task is fact-heavy or time-sensitive, prioritize Research.
2. If task is message-heavy, prioritize Structure.
3. If task is high-stakes, enforce Review before finalization.

## Output Contract

Each subagent should return:

1. `summary` - what was completed
2. `artifact` - the main output payload
3. `risks` - known uncertainty or weak points
4. `next_action` - single best next step

## Main-Agent Merge Policy

1. Reject outputs with unsupported strong claims.
2. Prefer evidence-backed conclusions when conflicts exist.
3. Keep one narrative line; remove duplicated or competing storylines.

## Failure Handling

If a subagent fails or returns weak output:

1. Downgrade target layer (for example, from full-deck-plan to planning-draft).
2. Record limitation clearly.
3. Continue with best possible artifact instead of blocking indefinitely.

