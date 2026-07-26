"""Hybrid retrieval — semantic + keyword search fusion (inspired by ConvoLens)."""

from __future__ import annotations

from backend.db import get_pool


async def hybrid_search(
    contact_id: str, query: str,
    semantic_weight: float = 0.6, keyword_weight: float = 0.4,
    limit: int = 10,
) -> list[dict]:
    """Search messages using hybrid fusion (semantic + keyword).

    Currently uses keyword matching as primary signal, with structure
    ready for pgvector semantic search when embeddings are populated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Keyword search via ILIKE (Chinese: no tsvector without zhparser)
        keywords = query.split()
        ilike_clauses = " OR ".join([f"content ILIKE '%' || ${i+2} || '%'" for i in range(len(keywords))])
        params = [contact_id] + keywords + [limit]

        rows = await conn.fetch(
            f"""SELECT content, role, timestamp, emotion, intent
                FROM messages
                WHERE contact_id = $1
                  AND ({ilike_clauses})
                ORDER BY timestamp DESC
                LIMIT ${len(keywords) + 2}""",
            *params,
        )
        return [
            {
                "content": r["content"],
                "role": r["role"],
                "timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                "emotion": r["emotion"],
                "intent": r["intent"],
            }
            for r in rows
        ]


async def search_memories(contact_id: str, query: str, limit: int = 5) -> list[dict]:
    """Search typed memories by content match."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT memory_type, content, confidence, importance
               FROM memories
               WHERE contact_id = $1 AND content ILIKE '%' || $2 || '%'
               ORDER BY importance DESC, confidence DESC
               LIMIT $3""",
            contact_id, query, limit,
        )
        return [
            {"memory_type": r["memory_type"], "content": r["content"],
             "confidence": r["confidence"], "importance": r["importance"]}
            for r in rows
        ]
