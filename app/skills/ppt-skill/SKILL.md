---
name: ppt-skill
description: >-
  Create or improve PPT/slide deliverables through a staged workflow. Use when
  the user asks for presentations, decks, storyboards, or slide-ready outputs
  (e.g. PPT、演示文稿、汇报、路演、答辩、培训课件), especially when success
  requires brief clarification, optional fact-finding, outline design, page-level
  planning, review gates, and graceful fallback under tool or environment limits.
---

# PPT Workflow Skill

## Overview

Treat PPT creation as staged work, not one-shot generation.  
Define what must happen and when. Leave implementation choices to the runtime environment.

Do not hard-code specific search/render/export tools unless the environment explicitly requires them.

## Quick Start

1. Clarify the brief with minimum required fields.
2. Decide whether fact-finding is necessary.
3. Build outline first, then planning draft (do not skip this middle layer on non-trivial decks).
4. Insert review gates for high-stakes decks.
5. Disclose capability limits and confidence boundaries.

If needed, read:
- `references/method.md` for staged method and quality checks.
- `references/agent-integration.md` for multi-agent coordination.
- `references/prompts.md` for reusable prompt templates.

## Capability Awareness

Before substantive work, determine at a high level whether the environment can:
- gather external facts or at least use user-supplied sources
- produce structured outputs (brief, outline, planning cards)
- generate reviewable artifacts
- deliver final files back to the user

Use this only to select an achievable layer. Do not turn it into a tool policy.

## Input Modes

### 1) Topic-only

If the request is under-specified, ask for minimal missing fields:
- audience
- purpose
- page-count range
- preferred tone/style
- whether fresh fact-finding is required
- whether staged review is preferred

### 2) Topic + brief

Proceed directly when audience, purpose, style, key messages, and page range are provided.

### 3) Source-driven request

Treat supplied reports/URLs/PDFs/notes as primary context.  
Use extra fact-finding only when it materially improves quality.

### 4) Existing outline or partial draft

Prefer targeted refinement over full regeneration.

## Output Layers (Stop at Needed Layer)

1. `research-brief`
2. `outline`
3. `planning-draft`
4. `sample-artifact`
5. `full-deck-plan`
6. `review-notes`

Each layer must be reviewable on its own.

## Default Workflow

### 1) Clarify Brief

Collect only what prevents avoidable misfire:
- topic
- audience
- purpose
- page-count range
- style/tone
- must-have sections
- must-avoid claims/directions
- rough-first vs staged-confirmation preference

### 2) Decide Fact-Finding Need

Do fact-finding before outlining when:
- the topic depends on current facts/statistics/product details
- user asks for research-backed content
- supplied material is incomplete

If not needed, proceed with provided context.

### 3) Gather/Organize Context

If external research is unavailable, state source limits and avoid invented certainty.

### 4) Produce Research Brief (When Relevant)

Summarize:
- key facts
- supporting evidence
- audience-relevant context
- caveats and unresolved questions

### 5) Generate Outline Before Design

Requirements:
- preserve section logic
- align claims with evidence confidence
- optimize for spoken explanation, not only reading
- keep output easy to review

### 6) Add Planning Draft

For non-trivial decks, provide page cards including:
- page objective
- key takeaway
- supporting info/evidence needed
- information hierarchy
- suggested visual structure

Do not jump from outline directly to polished final pages unless the task is explicitly trivial and user requests speed over controllability.

### 7) Provide Reviewable Intermediate Artifact

Artifact type is flexible: brief, outline, planning draft, or sample page representation.

### 8) Pause for Review on High-Stakes Decks

Use explicit review gates for:
- external-facing decks
- management/board decks
- customer/sales decks
- decks with uncertain or fast-moving facts
- complex technical topics

### 9) Scale or Finalize

Only expand after direction is accepted.

### 10) Final Check and Limitation Disclosure

Check:
- logic
- factual confidence
- evidence coverage
- density and emphasis
- cross-section consistency

If capability limits affected output, state this explicitly.

## Minimum Output Contract

For consistency, return structured sections:
1. `brief_summary` (topic, audience, purpose, constraints)
2. `output_layer` (current layer and why)
3. `artifact` (the actual layer output)
4. `assumptions_and_risks` (uncertain claims, missing data)
5. `next_step` (single best next action)

## Coordination Rules

### Research Rule

When confidence depends on facts, gather or verify sources before strong claims.

### Honesty Rule

If ideal workflow is unavailable, disclose limits and continue at the highest-value reachable layer.

### Review-Gate Rule

For complex or high-stakes requests, present intermediate work before full expansion.

### Non-Assumption Rule

Do not assume a specific research/render/export path.

## Resources

- `references/method.md` - staged method and quality checklist
- `references/agent-integration.md` - coordination contracts for main-agent/subagent setups
- `references/prompts.md` - reusable prompts for briefing, outline, planning, and review
