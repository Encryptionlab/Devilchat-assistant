"""Semantic dedup — ChromaDB embedding-based duplicate detection."""

from __future__ import annotations

from backend.db import _get_conn, get_chroma_collection


async def find_duplicates(
    content: str, contact_id: str, threshold: float = 0.15,
) -> list[dict]:
    """Find potentially duplicate memories by content similarity.

    Uses ChromaDB semantic search when embeddings are available,
    falls back to SQLite substring matching.
    """
    # Try ChromaDB semantic search
    try:
        coll = await get_chroma_collection("memories")
        results = coll.query(
            query_texts=[content],
            where={"contact_id": contact_id},
            n_results=5,
        )
        if results and results.get("ids") and results["ids"][0]:
            distances = results.get("distances", [[]])[0]
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else [[]] * len(ids)
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
            out = []
            for i, dist, doc, meta in zip(ids, distances, docs, metas):
                # cosine distance → similarity: 1 - dist. Low distance = high similarity.
                if dist <= threshold or content in doc:
                    out.append({
                        "id": i,
                        "memory_type": meta.get("memory_type", ""),
                        "content": doc,
                        "confidence": meta.get("confidence", 0.5),
                    })
            if out:
                return out
    except Exception:
        pass

    # Fallback to SQLite substring
    conn = await _get_conn()
    rows = await conn.execute(
        """SELECT id, memory_type, content, confidence
           FROM memories_sql
           WHERE contact_id = ?
             AND (content = ? OR content LIKE ? OR ? LIKE '%' || content || '%')
           LIMIT 5""",
        (contact_id, content, f"%{content}%", content),
    )
    return [
        {"id": r["id"], "memory_type": r["memory_type"],
         "content": r["content"], "confidence": r["confidence"]}
        async for r in rows
    ]


async def is_duplicate(content: str, contact_id: str, threshold: float = 0.15) -> bool:
    """Check if a memory with similar content already exists."""
    dupes = await find_duplicates(content, contact_id, threshold)
    return len(dupes) > 0
