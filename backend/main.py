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
    yield


app = FastAPI(title="魔鬼聊天 API", version="0.1.0", lifespan=lifespan)

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
    return {"status": "ok"}


from backend.routers import chat, conversations, relationship, bootstrap, observe
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(relationship.router)
app.include_router(bootstrap.router)
app.include_router(observe.router)
