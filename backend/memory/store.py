"""Typed memory CRUD — SQLite for metadata, ChromaDB for vector search."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta

from backend.db import _get_conn, get_chroma_collection

# ---------------------------------------------------------------------------
# Memory lifecycle configuration
# ---------------------------------------------------------------------------
_DECAY_CONFIG: dict[str, dict] = {
    "emotional_moment":  {"ttl_days": 30,   "decay_days": 7},
    "key_event":         {"ttl_days": 60,   "decay_days": 30},
    "shared_event":      {"ttl_days": 365,  "decay_days": None},
    "unresolved_issue":  {"ttl_days": 90,   "decay_days": 30},
    "preference":        {"ttl_days": 180,  "decay_days": None},
    "user_fact":         {"ttl_days": 365,  "decay_days": None},
    "recurring_topic":   {"ttl_days": 90,   "decay_days": 30},   # legacy
}

_TTL_MAP = {k: v["ttl_days"] for k, v in _DECAY_CONFIG.items()}


async def _delete_chroma_vectors(mem_ids: list[str]) -> int:
    """Remove vectors from ChromaDB. Best-effort — SQLite is source of truth."""
    if not mem_ids:
        return 0
    try:
        coll = await get_chroma_collection("memories")
        coll.delete(ids=mem_ids)
        return len(mem_ids)
    except Exception:
        return 0


async def store_memory(
    contact_id: str, memory_type: str, content: str,
    confidence: float = 0.5, importance: int = 1,
    evidence: list[dict] | None = None,
) -> str:
    """Insert a new typed memory. Returns memory_id."""
    mem_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    ttl_days = _TTL_MAP.get(memory_type, 365)
    expires = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

    conn = await _get_conn()
    await conn.execute(
        """INSERT INTO memories_sql (id, contact_id, memory_type, content, confidence, importance,
           evidence_messages, created_at, last_recalled_at, recall_count, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (mem_id, contact_id, memory_type, content, confidence, importance,
         json.dumps(evidence or [], ensure_ascii=False), now, now, expires),
    )
    await conn.commit()

    # Also add to ChromaDB for vector search
    try:
        coll = await get_chroma_collection("memories")
        coll.add(
            ids=[mem_id],
            documents=[content],
            metadatas=[{
                "contact_id": contact_id,
                "memory_type": memory_type,
                "confidence": confidence,
                "importance": importance,
            }],
        )
    except Exception:
        pass  # ChromaDB is best-effort; SQLite is the source of truth

    return mem_id


async def recall_memories(
    contact_id: str, memory_type: str | None = None,
    days: int = 30, limit: int = 10,
) -> list[dict]:
    """Recall top memories for a contact, optionally filtered by type and time."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conn = await _get_conn()
    if memory_type:
        rows = await conn.execute(
            """SELECT id, memory_type, content, confidence, importance, evidence_messages, created_at
               FROM memories_sql
               WHERE contact_id = ? AND memory_type = ? AND created_at > ?
               ORDER BY importance DESC, confidence DESC, recall_count DESC
               LIMIT ?""",
            (contact_id, memory_type, cutoff, limit),
        )
    else:
        rows = await conn.execute(
            """SELECT id, memory_type, content, confidence, importance, evidence_messages, created_at
               FROM memories_sql
               WHERE contact_id = ? AND created_at > ?
               ORDER BY importance DESC, confidence DESC, recall_count DESC
               LIMIT ?""",
            (contact_id, cutoff, limit),
        )

    result = []
    async for r in rows:
        result.append({
            "id": r["id"],
            "memory_type": r["memory_type"],
            "content": r["content"],
            "confidence": r["confidence"],
            "importance": r["importance"],
            "evidence": json.loads(r["evidence_messages"]) if r["evidence_messages"] else [],
            "created_at": r["created_at"],
        })
        # Update recall stats
        await conn.execute(
            "UPDATE memories_sql SET recall_count = recall_count + 1, last_recalled_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), r["id"]),
        )
    await conn.commit()
    return result


async def apply_decay(contact_id: str) -> dict:
    """Apply type-specific TTL expiry and confidence decay to memories.

    Called periodically (every ~15 messages) from the LangGraph pipeline.
    Deletes expired records from both SQLite and ChromaDB.
    Halves confidence for stale emotional/unresolved memories.
    """
    conn = await _get_conn()
    now = datetime.now(timezone.utc)
    deleted_ids: list[str] = []
    result: dict = {"deleted": {}, "decayed": {}}

    for mem_type, cfg in _DECAY_CONFIG.items():
        # TTL expiry: delete records past their lifespan
        cutoff = (now - timedelta(days=cfg["ttl_days"])).isoformat()
        cursor = await conn.execute(
            """DELETE FROM memories_sql
               WHERE contact_id = ? AND memory_type = ?
               AND (expires_at IS NOT NULL AND expires_at < ?
                    OR expires_at IS NULL AND created_at < ?)
               RETURNING id""",
            (contact_id, mem_type, now.isoformat(), cutoff),
        )
        rows = await cursor.fetchall()
        for row in rows:
            deleted_ids.append(row["id"])
        if rows:
            result["deleted"][mem_type] = len(rows)

        # Confidence decay: halve confidence for records past decay threshold
        decay_days = cfg.get("decay_days")
        if decay_days:
            decay_cutoff = (now - timedelta(days=decay_days)).isoformat()
            cur = await conn.execute(
                """UPDATE memories_sql
                   SET confidence = MAX(ROUND(confidence * 0.5, 4), 0.05)
                   WHERE contact_id = ? AND memory_type = ?
                   AND created_at < ? AND confidence > 0.05""",
                (contact_id, mem_type, decay_cutoff),
            )
            if cur.rowcount:
                result["decayed"][mem_type] = cur.rowcount

    await conn.commit()

    # Sync ChromaDB deletions
    if deleted_ids:
        await _delete_chroma_vectors(deleted_ids)

    return result
