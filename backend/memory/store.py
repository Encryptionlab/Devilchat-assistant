"""Typed memory CRUD — create, recall, update, decay."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from backend.db import get_pool


async def store_memory(
    contact_id: str, memory_type: str, content: str,
    confidence: float = 0.5, importance: int = 1,
    evidence: list[dict] | None = None,
) -> str:
    """Insert a new typed memory. Returns memory_id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        mem_id = await conn.fetchval(
            """INSERT INTO memories (contact_id, memory_type, content, confidence, importance, evidence_messages)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            contact_id, memory_type, content, confidence, importance,
            json.dumps(evidence or [], ensure_ascii=False),
        )
        return str(mem_id)


async def recall_memories(
    contact_id: str, memory_type: str | None = None,
    days: int = 30, limit: int = 10,
) -> list[dict]:
    """Recall top memories for a contact, optionally filtered by type and time."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, memory_type, content, confidence, importance, evidence_messages, created_at
               FROM memories
               WHERE contact_id = $1
                 AND ($2::varchar IS NULL OR memory_type = $2)
                 AND created_at > now() - ($3 || ' days')::interval
               ORDER BY importance DESC, confidence DESC, recall_count DESC
               LIMIT $4""",
            contact_id, memory_type, str(days), limit,
        )
        result = []
        for r in rows:
            result.append({
                "id": str(r["id"]),
                "memory_type": r["memory_type"],
                "content": r["content"],
                "confidence": r["confidence"],
                "importance": r["importance"],
                "evidence": json.loads(r["evidence_messages"]) if r["evidence_messages"] else [],
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            })
            # Update recall stats
            await conn.execute(
                "UPDATE memories SET recall_count = recall_count + 1, last_recalled_at = now() WHERE id = $1",
                r["id"],
            )
        return result


async def apply_decay(contact_id: str) -> dict:
    """Apply decay rules to memories."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # recurring_topic: 60 days → halve confidence, 90 days → delete
        result = await conn.execute(
            """DELETE FROM memories WHERE contact_id = $1
               AND memory_type = 'recurring_topic'
               AND created_at < now() - interval '90 days'""",
            contact_id,
        )
        deleted = int(result.split()[-1]) if result else 0

        await conn.execute(
            """UPDATE memories SET confidence = confidence * 0.5
               WHERE contact_id = $1 AND memory_type = 'recurring_topic'
               AND created_at < now() - interval '60 days'
               AND confidence > 0.1""",
            contact_id,
        )

        return {"deleted": deleted, "halved": "recurring_topic > 60 days"}
