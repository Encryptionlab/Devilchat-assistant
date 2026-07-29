"""WCF + Web Panel 启动入口 — 消息中继 + API + 观察管道一体化。

用法:
    python -m backend.main_wcf --target wxid_xxx
    python -m backend.main_wcf --target wxid_xxx --port 8000 --wcf-port 9999

然后浏览器打开 http://localhost:8000/api/wcf/panel
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.wcf.relay import WcfRelay
from backend.routers.wcf import router as wcf_router


def _parse_args():
    args = {"target": "", "port": 8000, "wcf_port": 10086}
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--target" and i + 1 < len(argv):
            args["target"] = argv[i + 1]
            i += 2
        elif argv[i] == "--port" and i + 1 < len(argv):
            args["port"] = int(argv[i + 1])
            i += 2
        elif argv[i] == "--wcf-port" and i + 1 < len(argv):
            args["wcf_port"] = int(argv[i + 1])
            i += 2
        else:
            i += 1
    return args


# Singleton relay
_relay: WcfRelay | None = None


async def _observe_handler(messages: list[dict]) -> dict:
    """Feed batched messages through the LangGraph observe pipeline."""
    try:
        from backend.graph.builder import get_graph
        from backend.db import resolve_contact_id, _get_conn
        import uuid as _uuid
        from datetime import datetime, timezone

        contact_id = await resolve_contact_id(_relay.config.target_wxid or "default")

        # Persist incoming messages immediately (graph observe path doesn't do this)
        conn = await _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        for msg in messages:
            await conn.execute(
                """INSERT INTO messages (id, contact_id, role, content, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(_uuid.uuid4()), contact_id,
                 msg.get("role", "她"), msg.get("content", ""), now),
            )
        await conn.commit()

        graph = get_graph()
        result = await graph.ainvoke(
            {
                "messages": messages,
                "mode": "observe",
                "contact_id": contact_id,
            },
            {"configurable": {"thread_id": _relay.config.target_wxid or "default"}},
        )
        return result
    except Exception:
        return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _relay
    try:
        from backend.db import init_schema
        await init_schema()
    except Exception:
        pass

    _relay = WcfRelay(
        target_wxid=app.state.wcf_target,
        port=app.state.wcf_port,
        poll_interval=1.5,
    )
    import backend.wcf.relay as relay_mod
    relay_mod._instance = _relay

    await _relay.start(observe_handler=_observe_handler)
    yield
    await _relay.stop()


def create_app(target_wxid: str = "", port: int = 8000, wcf_port: int = 9999) -> FastAPI:
    app = FastAPI(title="魔鬼聊天 WCF Panel", version="1.0.0", lifespan=lifespan)
    app.state.wcf_target = target_wxid
    app.state.wcf_port = wcf_port
    app.state.http_port = port

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()},
        )

    @app.get("/api/health")
    async def health():
        if _relay:
            return {"status": "ok", "relay": _relay.get_status()}
        return {"status": "starting"}

    app.include_router(wcf_router)
    return app


def main():
    args = _parse_args()
    if not args["target"]:
        print("用法: python -m backend.main_wcf --target wxid_xxx [--port 8000] [--wcf-port 10086]")
        print()
        print("请先通过 WCF 的 /api/get_contacts 获取对方的 wxid")
        print("或者运行时不指定 target，监听所有联系人")
        sys.exit(1)

    import uvicorn
    app = create_app(target_wxid=args["target"], port=args["port"], wcf_port=args["wcf_port"])
    print(f"\n{'='*50}")
    print(f"魔鬼聊天 WCF Panel 启动")
    print(f"  WCF API: http://127.0.0.1:{args['wcf_port']}")
    print(f"  Web 面板: http://localhost:{args['port']}/api/wcf/panel")
    print(f"  目标联系人: {args['target']}")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=args["port"], log_level="info")


if __name__ == "__main__":
    main()
