"""魔鬼聊天 — 新版 API 入口（LangGraph + SQLite + ChromaDB）。"""

import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.db import init_schema
        await init_schema()
        print("[INFO] SQLite + ChromaDB initialized")
    except Exception as e:
        print(f"[WARN] DB init failed: {e}")
    yield
    try:
        from backend.db import close_pool
        await close_pool()
    except Exception:
        pass


app = FastAPI(title="魔鬼聊天 API v2", version="0.3.0", lifespan=lifespan)

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
    db_ok = False
    try:
        from backend.db import _get_conn
        conn = await _get_conn()
        await conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass
    return {"status": "ok", "storage": "SQLite + ChromaDB", "database": db_ok, "version": "0.3.0"}


from backend.routers import graph
app.include_router(graph.router)
