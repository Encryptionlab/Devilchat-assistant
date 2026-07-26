"""FastAPI application entry point."""

import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.dependencies import init_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_services()
    # Initialize PostgreSQL schema on startup
    try:
        from backend.db import init_schema, close_pool
        await init_schema()
    except Exception:
        print("[WARN] PostgreSQL not available, using JSON fallback")
    yield
    try:
        from backend.db import close_pool
        await close_pool()
    except Exception:
        pass


app = FastAPI(title="魔鬼聊天 API", version="0.2.0", lifespan=lifespan)

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
    pg_ok = False
    try:
        from backend.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        pg_ok = True
    except Exception:
        pass
    return {"status": "ok", "postgresql": pg_ok, "version": "0.2.0"}


# Existing routes (JSON-based, backward compatible)
from backend.routers import chat, conversations, relationship, bootstrap, observe
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(relationship.router)
app.include_router(bootstrap.router)
app.include_router(observe.router)

# New graph-based routes
from backend.routers import graph
app.include_router(graph.router)
