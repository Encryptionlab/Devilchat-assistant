"""SQLite + ChromaDB 混合存储 — 结构化数据 + 向量语义搜索，均为嵌入式零配置。

SQLite (aiosqlite async): contacts, relationship_state, conversations, messages, strategy_metrics
ChromaDB (PersistentClient): memories (with embeddings), message_embeddings
"""

from __future__ import annotations

import json
import uuid
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite
import chromadb
from chromadb.config import Settings

from backend.config import DATA_DIR

SQLITE_PATH = os.path.join(DATA_DIR, "devilchat.db")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma")

# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

_conn: aiosqlite.Connection | None = None
_chroma_client: chromadb.PersistentClient | None = None
_memories_coll = None


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = await aiosqlite.connect(SQLITE_PATH)
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def _get_chroma() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


async def get_chroma_collection(name: str = "memories"):
    """Get or create a ChromaDB collection. Mainly used for vector search."""
    client = _get_chroma()
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    wxid TEXT UNIQUE NOT NULL,
    display_name TEXT
);

CREATE TABLE IF NOT EXISTS relationship_state (
    id TEXT PRIMARY KEY,
    contact_id TEXT UNIQUE REFERENCES contacts(id),
    stage TEXT NOT NULL DEFAULT 'acquaintance',
    trust_level INTEGER DEFAULT 50 CHECK (trust_level BETWEEN 0 AND 100),
    intimacy_level INTEGER DEFAULT 30 CHECK (intimacy_level BETWEEN 0 AND 100),
    conflict_level INTEGER DEFAULT 0 CHECK (conflict_level BETWEEN 0 AND 5),
    warmth TEXT DEFAULT 'neutral',
    personality_traits TEXT DEFAULT '[]',
    preferences TEXT DEFAULT '{}',
    future_events TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id),
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    goal TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    summary TEXT,
    outcome TEXT,
    key_points TEXT DEFAULT '[]',
    emotion_trajectory TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS memories_sql (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id),
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    evidence_messages TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    importance INTEGER DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    source TEXT DEFAULT 'auto',
    created_at TEXT DEFAULT (datetime('now')),
    last_recalled_at TEXT DEFAULT (datetime('now')),
    recall_count INTEGER DEFAULT 0,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    contact_id TEXT REFERENCES contacts(id),
    role TEXT NOT NULL CHECK (role IN ('我', '她')),
    content TEXT NOT NULL,
    emotion TEXT,
    intent TEXT,
    need_scores TEXT,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, timestamp);

CREATE TABLE IF NOT EXISTS strategy_metrics (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id),
    strategy_name TEXT NOT NULL,
    total_uses INTEGER DEFAULT 0,
    successes INTEGER DEFAULT 0,
    partials INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0,
    best_emotions TEXT DEFAULT '[]',
    worst_emotions TEXT DEFAULT '[]',
    last_used TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_metrics ON strategy_metrics(contact_id, strategy_name);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    checkpoint TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (thread_id, checkpoint_id)
);
"""


async def init_schema() -> None:
    conn = await _get_conn()
    await conn.executescript(SCHEMA_SQL)
    await conn.commit()
    # Ensure ChromaDB collection exists
    await get_chroma_collection("memories")


async def close_pool() -> None:
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


# ---------------------------------------------------------------------------
# Deprecated alias for close_pool
# ---------------------------------------------------------------------------

async def get_pool():
    """Deprecated: return the SQLite connection directly for backwards compat.
    Callers that used `pool.acquire() → conn` should now just await _get_conn().
    This wrapper returns an object with `.acquire()` for backwards compat.
    """
    return _SQLitePoolShim()


class _SQLitePoolShim:
    """Minimal shim so old `pool.acquire()` → `async with conn:` patterns work."""
    async def acquire(self):
        return _SQLiteConnCtx(await _get_conn())


class _SQLiteConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass  # Connection is shared, don't close per-use


# ---------------------------------------------------------------------------
# Contact helpers
# ---------------------------------------------------------------------------

async def ensure_contact(wxid: str = "default", display_name: str = "她") -> str:
    conn = await _get_conn()
    row = await conn.execute("SELECT id FROM contacts WHERE wxid = ?", (wxid,))
    existing = await row.fetchone()
    if existing:
        return existing["id"]
    cid = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO contacts (id, wxid, display_name) VALUES (?, ?, ?)",
        (cid, wxid, display_name),
    )
    await conn.commit()
    return cid


async def resolve_contact_id(contact_id: str) -> str:
    """Resolve a contact identifier (wxid or UUID) to a valid UUID string."""
    import uuid as _uuid
    try:
        _uuid.UUID(contact_id)
        conn = await _get_conn()
        row = await conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,))
        if await row.fetchone():
            return contact_id
    except ValueError:
        pass
    return await ensure_contact(wxid=contact_id)


# ---------------------------------------------------------------------------
# Memory helpers (SQLite fallback for ChromaDB-less operations)
# ---------------------------------------------------------------------------

async def sqlite_fetch(sql: str, *params) -> list[dict]:
    conn = await _get_conn()
    cursor = await conn.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def sqlite_execute(sql: str, *params) -> int:
    conn = await _get_conn()
    cursor = await conn.execute(sql, params)
    await conn.commit()
    return cursor.rowcount


async def sqlite_fetch_one(sql: str, *params) -> dict | None:
    conn = await _get_conn()
    cursor = await conn.execute(sql, params)
    row = await cursor.fetchone()
    return dict(row) if row else None


async def sqlite_insert(sql: str, *params) -> str:
    """INSERT and return the generated id."""
    conn = await _get_conn()
    cursor = await conn.execute(sql, params)
    await conn.commit()
    return cursor.lastrowid
