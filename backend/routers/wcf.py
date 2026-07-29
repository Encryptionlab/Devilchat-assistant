"""WCF web panel API — message stream, status, manual reply."""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from pathlib import Path

router = APIRouter(prefix="/api/wcf", tags=["wcf"])


class ReplyRequest(BaseModel):
    text: str


def _get_relay():
    """Get the global relay instance (set by startup)."""
    import backend.wcf.relay as mod
    relay = getattr(mod, "_instance", None)
    if relay is None:
        raise HTTPException(status_code=503, detail="WCF relay not started")
    return relay


@router.get("/status")
async def wcf_status():
    """Relay health + stats + latest pipeline state."""
    return _get_relay().get_status()


@router.get("/messages")
async def wcf_messages(n: int = 50):
    """Recent buffered messages with pipeline annotations."""
    return _get_relay().get_recent_messages(n)


@router.post("/reply")
async def wcf_reply(req: ReplyRequest):
    """Queue a manual text reply to the target contact."""
    relay = _get_relay()
    wxid = relay.config.target_wxid
    if not wxid:
        raise HTTPException(status_code=400, detail="target_wxid not configured")
    relay.queue_reply(wxid, req.text)
    return {"queued": True, "wxid": wxid, "text": req.text}


@router.post("/reply/{wxid}")
async def wcf_reply_to(wxid: str, req: ReplyRequest):
    """Queue a reply to a specific wxid."""
    _get_relay().queue_reply(wxid, req.text)
    return {"queued": True, "wxid": wxid, "text": req.text}


@router.get("/contacts")
async def wcf_contacts():
    """List all WeChat contacts."""
    relay = _get_relay()
    return relay.client.get_contacts()


@router.get("/events")
async def wcf_events():
    """SSE stream: push new messages to web panel in real time."""

    async def _stream():
        import asyncio
        relay = _get_relay()
        last_count = relay._stats["total_received"]
        while relay._running:
            current = relay._stats["total_received"]
            if current > last_count:
                new_msgs = [
                    m for m in relay.get_recent_messages(current - last_count + 1)
                    if m["role"] == "她"
                ]
                if new_msgs:
                    yield f"data: {json.dumps(new_msgs, ensure_ascii=False)}\n\n"
                last_count = current
            await asyncio.sleep(0.5)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/panel", response_class=HTMLResponse)
async def wcf_panel():
    """Serve the lightweight web panel."""
    panel_path = Path(__file__).parent.parent.parent / "web" / "panel.html"
    if not panel_path.exists():
        return HTMLResponse("<h1>Panel not found</h1>", status_code=404)
    return HTMLResponse(panel_path.read_text(encoding="utf-8"))
