"""WCF message relay — WeChatFerry → observe pipeline → manual reply.

Architecture:
  WeChatFerry DLL (:10086) → thread drains messages into queue
    → poll loop feeds batches to observe pipeline (LangGraph)
    → web panel displays buffered messages with emotion/topic tags
    → user types reply → WcfClient.send_text → WeChatFerry → 微信

Usage:
    relay = WcfRelay(target_wxid="wxid_xxx")
    await relay.start(observe_handler=my_handler)
    await relay.stop()
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

from backend.wcf.client import WcfClient, WcfConfig

MAX_BUFFER = 200
LOG_DIR = Path(__file__).parent.parent.parent / "data" / "wcf_logs"


@dataclass
class BufferedMessage:
    raw: dict
    role: str  # "她" or "我"
    timestamp: str
    emotion: str = ""
    topic: str = ""
    reply_candidate: str = ""
    reply_sent: bool = False


# Singleton relay for the web panel to access
_instance: "WcfRelay | None" = None


class WcfRelay:
    def __init__(self, target_wxid: str = "", port: int = 10086, poll_interval: float = 1.0):
        self.config = WcfConfig(target_wxid=target_wxid, port=port, poll_interval=poll_interval)
        self.client = WcfClient(self.config)
        self.buffer: deque[BufferedMessage] = deque(maxlen=MAX_BUFFER)
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_her_message: Callable[[list[dict]], Awaitable[dict]] | None = None
        self._pending_replies: dict[str, str] = {}
        self._stats = {
            "total_received": 0,
            "her_messages": 0,
            "my_messages": 0,
            "replies_sent": 0,
            "errors": 0,
            "start_time": None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, observe_handler: Callable[[list[dict]], Awaitable[dict]] | None = None):
        """Connect to WeChatFerry, start polling loop."""
        self._on_her_message = observe_handler
        self._stats["start_time"] = time.time()

        ok = await asyncio.to_thread(self.client.start)
        if not ok:
            raise RuntimeError("WeChatFerry 连接失败：请确认微信已登录且 DLL 已注入")

        info = self.client.get_self_info()
        contacts = self.client.get_contacts()
        print(f"[WCF] 已登录: {info.get('name', info.get('wxid', '?'))}")
        if self.config.target_wxid:
            match = [c for c in contacts if c.get("wxid") == self.config.target_wxid]
            print(f"[WCF] 目标: {match[0].get('name', self.config.target_wxid) if match else '未找到'}")
        print(f"[WCF] 联系人: {len(contacts)}, 开始监听...")

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self.client.stop)
        self._save_log()

    async def _poll_loop(self):
        batch: list[dict] = []
        last_flush = time.time()

        while self._running:
            try:
                new_msgs = await asyncio.to_thread(self.client.poll_messages)
            except Exception:
                new_msgs = []

            if new_msgs:
                for raw in new_msgs:
                    self._stats["total_received"] += 1
                    role = "我" if raw.get("is_self") else "她"
                    if role != "她":
                        continue

                    self._stats["her_messages"] += 1
                    bm = BufferedMessage(
                        raw=raw,
                        role=role,
                        timestamp=self._ts_to_iso(raw.get("ts", 0)),
                    )
                    self.buffer.append(bm)
                    batch.append({"role": role, "content": raw.get("content", "")})

                now = time.time()
                if batch and (len(batch) >= 5 or now - last_flush > 5.0):
                    await self._flush_batch(batch)
                    batch = []
                    last_flush = now

            await self._process_replies()
            await asyncio.sleep(self.config.poll_interval)

    async def _flush_batch(self, batch: list[dict]):
        if not self._on_her_message:
            return
        try:
            result = await self._on_her_message(batch)
            if result:
                emotion = result.get("emotion", "")
                topic = result.get("topic", "")
                for bm in list(self.buffer)[-len(batch):]:
                    bm.emotion = emotion or bm.emotion
                    bm.topic = topic or bm.topic
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[WCF] Pipeline error: {e}")

    async def _process_replies(self):
        if not self._pending_replies:
            return
        for wxid, text in list(self._pending_replies.items()):
            try:
                ok = await asyncio.to_thread(self.client.send_text, wxid, text)
                if ok:
                    self._stats["replies_sent"] += 1
                    for bm in reversed(self.buffer):
                        if bm.role == "她" and not bm.reply_sent:
                            bm.reply_candidate = text
                            bm.reply_sent = True
                            break
                else:
                    print(f"[WCF] 发送失败: {wxid}")
            except Exception as e:
                self._stats["errors"] += 1
                print(f"[WCF] Send error: {e}")
            del self._pending_replies[wxid]

    # ------------------------------------------------------------------
    # API for web panel
    # ------------------------------------------------------------------

    def queue_reply(self, wxid: str, text: str):
        self._pending_replies[wxid] = text

    def get_status(self) -> dict:
        s = {**self._stats}
        s.update(self.client.health_check())
        s["buffer_size"] = len(self.buffer)
        s["running"] = self._running
        s["pending_replies"] = len(self._pending_replies)
        last_e = ""
        last_t = ""
        for bm in reversed(self.buffer):
            if bm.role == "她":
                last_e = bm.emotion or last_e
                last_t = bm.topic or last_t
                if last_e:
                    break
        s["last_emotion"] = last_e
        s["last_topic"] = last_t
        return s

    def get_recent_messages(self, n: int = 50) -> list[dict]:
        return [
            {
                "role": bm.role,
                "content": bm.raw.get("content", ""),
                "timestamp": bm.timestamp,
                "emotion": bm.emotion,
                "topic": bm.topic,
                "reply_sent": bm.reply_sent,
                "reply_text": bm.reply_candidate,
            }
            for bm in list(self.buffer)[-n:]
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ts_to_iso(ts) -> str:
        from datetime import datetime, timezone
        try:
            if isinstance(ts, int) and ts > 1000000000:
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            pass
        return str(ts)

    def _save_log(self):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            fname = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
            data = self.get_recent_messages(MAX_BUFFER)
            (LOG_DIR / fname).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
