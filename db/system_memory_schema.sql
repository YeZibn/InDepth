-- System Memory SQLite schema (v1)
-- Created: 2026-04-10

CREATE TABLE IF NOT EXISTS memory_trigger_event (
    event_id TEXT PRIMARY KEY,
    event_time TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    context_id TEXT,
    risk_level TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_retrieval_event (
    event_id TEXT PRIMARY KEY,
    event_time TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger_event_id TEXT,
    memory_id TEXT,
    score REAL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_decision_event (
    event_id TEXT PRIMARY KEY,
    event_time TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger_event_id TEXT,
    memory_id TEXT,
    decision TEXT,
    reason TEXT,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mem_trigger_time ON memory_trigger_event(event_time);
CREATE INDEX IF NOT EXISTS idx_mem_retrieval_trigger_id ON memory_retrieval_event(trigger_event_id);
CREATE INDEX IF NOT EXISTS idx_mem_decision_trigger_id ON memory_decision_event(trigger_event_id);
CREATE INDEX IF NOT EXISTS idx_mem_decision_memory_id ON memory_decision_event(memory_id);

CREATE TABLE IF NOT EXISTS memory_card (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    scenario_stage TEXT NOT NULL,
    trigger_hint TEXT NOT NULL,
    problem_pattern_json TEXT NOT NULL,
    solution_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    anti_pattern_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    impact_json TEXT NOT NULL,
    owner_team TEXT NOT NULL,
    owner_primary TEXT NOT NULL,
    owner_reviewers_json TEXT NOT NULL,
    status TEXT NOT NULL,
    version TEXT NOT NULL,
    effective_from TEXT,
    expire_at TEXT,
    last_reviewed_at TEXT,
    confidence TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_memory_card_stage_status ON memory_card(scenario_stage, status);
CREATE INDEX IF NOT EXISTS idx_memory_card_expire_at ON memory_card(expire_at);
CREATE INDEX IF NOT EXISTS idx_memory_card_title_domain ON memory_card(title, domain);
