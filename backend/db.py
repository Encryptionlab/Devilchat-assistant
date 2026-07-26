"""PostgreSQL + pgvector connection pool and schema management."""

from __future__ import annotations

import asyncpg
from backend.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wxid VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS relationship_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id) UNIQUE,
    stage VARCHAR(50) NOT NULL DEFAULT 'acquaintance',
    trust_level INT DEFAULT 50 CHECK (trust_level BETWEEN 0 AND 100),
    intimacy_level INT DEFAULT 30 CHECK (intimacy_level BETWEEN 0 AND 100),
    conflict_level INT DEFAULT 0 CHECK (conflict_level BETWEEN 0 AND 5),
    warmth VARCHAR(20) DEFAULT 'neutral',
    personality_traits JSONB DEFAULT '[]',
    preferences JSONB DEFAULT '{}',
    future_events JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id),
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    evidence_messages JSONB DEFAULT '[]',
    confidence FLOAT DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    embedding VECTOR(1536),
    importance INT DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    source VARCHAR(50) DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_recalled_at TIMESTAMPTZ DEFAULT now(),
    recall_count INT DEFAULT 0,
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id),
    topic VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    goal VARCHAR(100),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    summary TEXT,
    outcome VARCHAR(50),
    key_points JSONB DEFAULT '[]',
    emotion_trajectory JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    contact_id UUID REFERENCES contacts(id),
    role VARCHAR(10) NOT NULL CHECK (role IN ('我', '她')),
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    emotion VARCHAR(50),
    intent VARCHAR(50),
    need_scores JSONB,
    timestamp TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, timestamp);

CREATE TABLE IF NOT EXISTS strategy_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id),
    strategy_name VARCHAR(255) NOT NULL,
    total_uses INT DEFAULT 0,
    successes INT DEFAULT 0,
    partials INT DEFAULT 0,
    failures INT DEFAULT 0,
    success_rate FLOAT DEFAULT 0,
    best_emotions JSONB DEFAULT '[]',
    worst_emotions JSONB DEFAULT '[]',
    last_used TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_metrics ON strategy_metrics(contact_id, strategy_name);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_id VARCHAR(255) NOT NULL,
    parent_checkpoint_id VARCHAR(255),
    checkpoint JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME,
            min_size=2, max_size=10,
        )
    return _pool


async def init_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def ensure_contact(wxid: str = "default", display_name: str = "她") -> str:
    """Ensure a contact row exists, return contact_id (UUID string)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM contacts WHERE wxid = $1", wxid
        )
        if row:
            return str(row["id"])
        return str(await conn.fetchval(
            "INSERT INTO contacts (wxid, display_name) VALUES ($1, $2) RETURNING id",
            wxid, display_name,
        ))


async def resolve_contact_id(contact_id: str) -> str:
    """Resolve a contact identifier (wxid or UUID string) to a valid UUID string.

    If it looks like a UUID format, verify it exists. Otherwise, treat as wxid
    and call ensure_contact.
    """
    import uuid as _uuid
    try:
        _uuid.UUID(contact_id)
        # It's a UUID — verify it exists
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM contacts WHERE id = $1", contact_id)
            if row:
                return contact_id
    except ValueError:
        pass
    # Not a UUID — treat as wxid
    return await ensure_contact(wxid=contact_id)
