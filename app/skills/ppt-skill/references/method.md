# PPT Agent Workflow Method

## Core Thesis

A strong PPT agent is not a one-shot slide generator.  
It should behave like a small presentation team:

`需求澄清 -> 资料调研 -> 大纲规划 -> 策划稿 -> 设计稿 -> 复核`

The reusable value is the staged method plus clear hand-offs between stages.

## Distilled Ideas

### 1) Start from questions, not templates

Do not jump from topic to visual pages. Ask first:

- 给谁看
- 为什么做
- 希望对方记住或接受什么
- 哪些事实不能说错
- 需要多新、多准的调研

### 2) Content leads, design follows

Delay polished visuals until the storyline is sound.  
PPT quality is primarily determined by content logic and evidence fitness.

### 3) Keep the missing middle: planning draft (策划稿)

Do not jump directly from outline to styled pages.

Each planning card should include:
- page purpose
- key message
- evidence basis
- recommended expression form
- hierarchy/layout direction

### 4) Use an explicit layout language

Describe pages as cards/containers/hierarchy/spacing, not rigid templates.  
Let content structure drive layout choice and emphasis.

### 5) Prefer structured outputs between stages

Typical chain:

1. brief notes -> research brief
2. research brief -> outline JSON
3. outline JSON -> planning draft
4. planning draft -> sample pages
5. approved sample -> scale up

## Suggested Deliverable Layers

Stop at the layer the user needs:

1. `research-brief`
2. `outline`
3. `planning-draft`
4. `sample-artifact`
5. `full-deck-plan`
6. `review-notes`

## Quality Bar

A strong run should produce:

1. clear argument flow
2. fewer decorative but empty pages
3. evidence-grounded claims when research exists
4. controllable page planning via planning drafts
5. reviewable mid-state artifacts before scaling

## Evidence and Confidence Rules

1. Mark uncertainty explicitly.
2. Avoid invented numbers, dates, and product facts.
3. If research is limited, state "source-limited" and continue with available inputs.

## Review Gate Guidance

Use mandatory review gates for:

1. external-facing decks
2. management/board communication
3. customer/sales decks
4. technical topics with high correctness risk
5. topics relying on fast-moving facts

## Fallback Strategy

When capabilities are limited:

1. keep stage order but reduce depth
2. deliver the highest reachable layer
3. disclose missing capability and impact
4. suggest one concrete next step
