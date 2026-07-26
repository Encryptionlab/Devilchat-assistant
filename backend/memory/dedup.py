"""Semantic dedup — embedding-based duplicate detection (inspired by Threa PR #1131)."""

from __future__ import annotations

from backend.db import get_pool


async def find_duplicates(
    content: str, contact_id: str, threshold: float = 0.15,
) -> list[dict]:
    """Find potentially duplicate memories by content similarity.

    Current implementation uses exact substring matching as a lightweight
    stand-in for embedding cosine distance. Upgrade to pgvector <=> when
    embedding pipeline is active.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, memory_type, content, confidence
               FROM memories
               WHERE contact_id = $1
                 AND (content = $2 OR content ILIKE '%' || $2 || '%'
                      OR $2 ILIKE '%' || content || '%')
               LIMIT 5""",
            contact_id, content,
        )
        return [
            {"id": r["id"], "memory_type": r["memory_type"],
             "content": r["content"], "confidence": r["confidence"]}
            for r in rows
        ]


async def is_duplicate(content: str, contact_id: str, threshold: float = 0.15) -> bool:
    """Check if a memory with similar content already exists."""
    dupes = await find_duplicates(content, contact_id, threshold)
    return len(dupes) > 0
