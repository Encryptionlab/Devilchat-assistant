"""One-shot data migration: JSON files → PostgreSQL."""

import asyncio
import json
from pathlib import Path
from backend.db import init_schema, get_pool, ensure_contact, close_pool
from backend.config import RS_PATH, CONV_PATH

ROOT_DIR = Path(__file__).parent.parent


async def migrate() -> None:
    await init_schema()
    contact_id = await ensure_contact(wxid="default", display_name="她")
    print(f"Contact: {contact_id}")

    # Migrate relationship_state.json
    if RS_PATH.exists():
        raw = json.loads(RS_PATH.read_text(encoding="utf-8"))
        rs = raw.get("relationship_state", raw)
        await _migrate_rs(contact_id, rs)
        print(f"Migrated relationship_state: stage={rs.get('stage')}")

    # Migrate conversations.json
    if CONV_PATH.exists():
        conv_data = json.loads(CONV_PATH.read_text(encoding="utf-8"))
        await _migrate_conversations(contact_id, conv_data)
        print(f"Migrated conversations: {len(conv_data.get('closed', []))} closed")

    # Migrate strategy_effectiveness → strategy_metrics
    if RS_PATH.exists():
        raw = json.loads(RS_PATH.read_text(encoding="utf-8"))
        rs = raw.get("relationship_state", raw)
        eff = rs.get("strategy_effectiveness", {})
        await _migrate_strategy_metrics(contact_id, eff)
        print(f"Migrated strategy metrics: {len(eff)} strategies")

    await close_pool()
    print("Migration complete.")


async def _migrate_rs(contact_id: str, rs: dict) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO relationship_state (contact_id, stage, trust_level, intimacy_level, conflict_level, warmth)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (contact_id) DO UPDATE SET
                 stage = EXCLUDED.stage, trust_level = EXCLUDED.trust_level,
                 intimacy_level = EXCLUDED.intimacy_level, conflict_level = EXCLUDED.conflict_level,
                 warmth = EXCLUDED.warmth""",
            contact_id,
            rs.get("stage", "acquaintance"),
            rs.get("trust_level", 50),
            rs.get("intimacy_level", rs.get("closeness_level", 30)),
            rs.get("conflict_level", 0),
            rs.get("warmth", "neutral"),
        )

        # Migrate 近期关键事件 → memories
        for evt in rs.get("近期关键事件", [])[:10]:
            await conn.execute(
                """INSERT INTO memories (contact_id, memory_type, content, confidence, importance, source)
                   VALUES ($1, 'shared_event', $2, 0.7, 2, 'migration')""",
                contact_id, str(evt),
            )

        # Migrate recurring_topics → memories
        for topic in rs.get("recurring_topics", []):
            await conn.execute(
                """INSERT INTO memories (contact_id, memory_type, content, confidence, source)
                   VALUES ($1, 'recurring_topic', $2, 0.6, 'migration')""",
                contact_id, str(topic),
            )

        # Migrate unresolved_topics → memories
        for issue in rs.get("unresolved_topics", []):
            await conn.execute(
                """INSERT INTO memories (contact_id, memory_type, content, confidence, importance, source)
                   VALUES ($1, 'unresolved_issue', $2, 0.7, 3, 'migration')""",
                contact_id, str(issue),
            )


async def _migrate_conversations(contact_id: str, conv_data: dict) -> None:
    from datetime import datetime, timezone
    pool = await get_pool()
    async with pool.acquire() as conn:
        for conv in conv_data.get("closed", [])[:50]:
            st = conv.get("start_time", "2026-07-01T00:00:00")
            et = conv.get("end_time", "2026-07-01T00:00:00")
            try:
                st_dt = datetime.fromisoformat(st)
                et_dt = datetime.fromisoformat(et)
            except (ValueError, TypeError):
                st_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
                et_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)

            conv_id = await conn.fetchval(
                """INSERT INTO conversations (contact_id, topic, status, goal, start_time, end_time, summary, outcome, key_points)
                   VALUES ($1, $2, 'closed', $3, $4, $5, $6, $7, $8)
                   RETURNING id""",
                contact_id,
                conv.get("topic", "daily"),
                conv.get("current_goal", ""),
                st_dt, et_dt,
                conv.get("summary", ""),
                conv.get("outcome", "neutral"),
                json.dumps(conv.get("key_points", []), ensure_ascii=False),
            )
            for msg in conv.get("messages_log", []):
                ts = msg.get("timestamp", "2026-07-01T00:00:00")
                try:
                    ts_dt = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
                await conn.execute(
                    """INSERT INTO messages (conversation_id, contact_id, role, content, timestamp)
                       VALUES ($1, $2, $3, $4, $5)""",
                    conv_id, contact_id,
                    msg.get("role", "她"), msg.get("content", ""),
                    ts_dt,
                )


async def _migrate_strategy_metrics(contact_id: str, eff: dict) -> None:
    from datetime import datetime, timezone
    pool = await get_pool()
    async with pool.acquire() as conn:
        for name, entry in eff.items():
            if isinstance(entry, dict):
                lu = entry.get("last_used", "2026-07-01T00:00:00")
                try:
                    lu_dt = datetime.fromisoformat(lu)
                except (ValueError, TypeError):
                    lu_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
                await conn.execute(
                    """INSERT INTO strategy_metrics (contact_id, strategy_name, total_uses, successes, partials, failures, success_rate, last_used)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT (contact_id, strategy_name) DO UPDATE SET
                         total_uses = EXCLUDED.total_uses, successes = EXCLUDED.successes,
                         partials = EXCLUDED.partials, failures = EXCLUDED.failures,
                         success_rate = EXCLUDED.success_rate, last_used = EXCLUDED.last_used""",
                    contact_id, name,
                    entry.get("total_uses", 0), entry.get("successes", 0),
                    entry.get("partials", 0), entry.get("failures", 0),
                    entry.get("success_rate", 0.0),
                    lu_dt,
                )


if __name__ == "__main__":
    asyncio.run(migrate())
