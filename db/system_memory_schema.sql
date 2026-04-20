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
    recall_hint TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    expire_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_memory_card_status ON memory_card(status);
CREATE INDEX IF NOT EXISTS idx_memory_card_expire_at ON memory_card(expire_at);
CREATE INDEX IF NOT EXISTS idx_memory_card_title ON memory_card(title);
