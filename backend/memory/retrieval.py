"""Hybrid retrieval — ChromaDB semantic search + SQLite keyword fallback."""

from __future__ import annotations

from backend.db import _get_conn, get_chroma_collection


async def hybrid_search(
    contact_id: str, query: str,
    semantic_weight: float = 0.6, keyword_weight: float = 0.4,
    limit: int = 10,
) -> list[dict]:
    """Search messages using keyword matching.

    When embeddings are populated, ChromaDB semantic search takes over
    via search_memories(). This function handles keyword fallback on the
    messages table.
    """
    conn = await _get_conn()
    keywords = [k for k in query.split() if k]
    if not keywords:
        rows = await conn.execute(
            """SELECT content, role, timestamp, emotion, intent
               FROM messages WHERE contact_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (contact_id, limit),
        )
    else:
        clauses = " OR ".join(["content LIKE ?" for _ in keywords])
        params = [contact_id] + [f"%{k}%" for k in keywords] + [limit]
        rows = await conn.execute(
            f"""SELECT content, role, timestamp, emotion, intent
                FROM messages
                WHERE contact_id = ? AND ({clauses})
                ORDER BY timestamp DESC LIMIT ?""",
            params,
        )

    return [
        {
            "content": r["content"],
            "role": r["role"],
            "timestamp": r["timestamp"],
            "emotion": r["emotion"],
            "intent": r["intent"],
        }
        async for r in rows
    ]


async def search_memories(contact_id: str, query: str, limit: int = 5) -> list[dict]:
    """Semantic search via ChromaDB, with SQLite keyword fallback."""
    # Try ChromaDB semantic search first
    try:
        coll = await get_chroma_collection("memories")
        results = coll.query(
            query_texts=[query],
            where={"contact_id": contact_id},
            n_results=limit,
        )
        if results and results.get("ids") and results["ids"][0]:
            out = []
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else [[]] * len(ids)
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
            for i, doc, meta in zip(ids, docs, metas):
                out.append({
                    "id": i,
                    "memory_type": meta.get("memory_type", ""),
                    "content": doc,
                    "confidence": meta.get("confidence", 0.5),
                    "importance": meta.get("importance", 1),
                })
            return out
    except Exception:
        pass

    # Fallback to SQLite keyword search
    conn = await _get_conn()
    rows = await conn.execute(
        """SELECT id, memory_type, content, confidence, importance
           FROM memories_sql
           WHERE contact_id = ? AND content LIKE ?
           ORDER BY importance DESC, confidence DESC
           LIMIT ?""",
        (contact_id, f"%{query}%", limit),
    )
    return [
        {"id": r["id"], "memory_type": r["memory_type"], "content": r["content"],
         "confidence": r["confidence"], "importance": r["importance"]}
        async for r in rows
    ]
