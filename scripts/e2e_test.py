"""E2E test v2: verify reply length fix + memory extraction."""
import asyncio, json, sys, time, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

TARGET_WXID = "wxid_5qyz6dc2i4p322"


async def load_messages():
    from backend.db import _get_conn
    conn = await _get_conn()
    conn.row_factory = __import__("aiosqlite").Row
    cur = await conn.execute(
        "SELECT id, role, content, timestamp FROM messages WHERE contact_id = (SELECT id FROM contacts WHERE wxid = ?) ORDER BY timestamp ASC",
        (TARGET_WXID,),
    )
    rows = [r async for r in cur]
    return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in rows]


async def test_intervene():
    from backend.graph.builder import get_graph
    from backend.db import resolve_contact_id

    messages = await load_messages()
    print(f"Loaded {len(messages)} messages from SQLite")

    contact_id = await resolve_contact_id(TARGET_WXID)
    graph = get_graph()

    # Use last 25 messages as context window
    ctx = messages[-25:]
    print(f"Running intervene pipeline with {len(ctx)} messages...")
    t0 = time.time()

    result = await graph.ainvoke(
        {"messages": ctx, "mode": "intervene", "contact_id": contact_id},
        {"configurable": {"thread_id": f"{TARGET_WXID}_e2e_v2"}},
    )

    elapsed = time.time() - t0
    print(f"Pipeline completed in {elapsed:.1f}s")

    # Results
    print(f"\n--- Analysis ---")
    for f in ["emotion", "emotion_intensity", "dominant_need", "topic", "burst_pattern", "goal_zh", "strategy_name"]:
        v = result.get(f, "")
        if v:
            print(f"  {f}: {v}")

    print(f"\n--- Generated Reply ---")
    reply = result.get("reply", "")
    print(f"  reply ({len(reply)} chars): {reply[:300]}")
    enhanced = result.get("enhanced_reply", "")
    print(f"  enhanced ({len(enhanced)} chars): {enhanced[:300]}")

    print(f"\n--- Memory Extraction ---")
    extracted = result.get("_extracted_memories", [])
    msg_count = result.get("_msg_count_since_extract", "N/A")
    print(f"  msg_count_since_extract: {msg_count}")
    print(f"  extracted_memories: {len(extracted)}")
    for m in extracted:
        print(f"    [{m.get('memory_type','?')}] {m.get('content','')[:80]} (confidence={m.get('confidence',0)})")

    # DB check
    from backend.db import _get_conn, get_chroma_collection
    conn = await _get_conn()
    conn.row_factory = __import__("aiosqlite").Row
    cur = await conn.execute("SELECT COUNT(*) as c FROM memories_sql")
    sql_count = (await cur.fetchone())["c"]
    try:
        coll = await get_chroma_collection("memories")
        chroma_count = coll.count()
    except Exception:
        chroma_count = "error"
    print(f"\n--- Persistence ---")
    print(f"  SQLite memories_sql: {sql_count} rows")
    print(f"  ChromaDB memories: {chroma_count} vectors")

    # Verdict
    print(f"\n--- Verdict ---")
    checks = []
    checks.append(("reply > 100 chars (addressing complex input)", len(reply) >= 100))
    checks.append(("enhanced doesn't destroy content", len(enhanced) >= len(reply) * 0.4))
    checks.append(("memory extraction triggered", len(extracted) > 0 or msg_count != "N/A"))
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")

    all_ok = all(ok for _, ok in checks)
    print(f"\n  Overall: {'ALL PASSED' if all_ok else 'SOME FAILED'}")
    return result


async def main():
    from backend.db import init_schema
    await init_schema()
    await test_intervene()

asyncio.run(main())
