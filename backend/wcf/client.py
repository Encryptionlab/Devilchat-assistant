"""WeChatFerry client wrapper — Python SDK for WeChatFerry DLL.

WeChatFerry: lich0821/WeChatFerry v39.5.2 (archived 2026-07-10)
Supported WeChat: 3.9.12.51
Protocol: gRPC + nanomsg over local TCP (default port 10086)
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional
from queue import Queue, Empty


@dataclass
class WcfConfig:
    host: str | None = None  # None = local mode (load sdk.dll, inject into WeChat)
    port: int = 10086
    target_wxid: str = ""
    poll_interval: float = 0.5


class WcfClient:
    """Wrapper around wcferry.Wcf for buffer-based message polling.

    WeChatFerry uses a background thread + Queue for message delivery.
    This wrapper drains the queue periodically and returns normalized
    message dicts compatible with our pipeline.
    """

    def __init__(self, config: WcfConfig | None = None):
        self.cfg = config or WcfConfig()
        self._wcf = None
        self._started = False
        self._msg_queue: Queue = Queue()
        self._buffer: list[dict] = []
        self._last_ts: int = 0
        self._contacts: list[dict] = []
        self._my_wxid: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Connect to the WeChatFerry DLL and start receiving messages."""
        from wcferry import Wcf

        self._wcf = Wcf(host=self.cfg.host, port=self.cfg.port, debug=True, block=True)

        self._my_wxid = self._wcf.get_self_wxid()
        self._contacts = self._wcf.get_contacts()
        self._wcf.enable_receiving_msg(pyq=False)

        # Background thread: drain WeChatFerry internal queue into ours
        self._started = True
        t = threading.Thread(target=self._drain_loop, daemon=True, name="wcf-drain")
        t.start()
        return True

    def stop(self):
        self._started = False

    def _drain_loop(self):
        """Continuously pull messages from wcferry into our own buffer."""
        while self._started:
            try:
                msg = self._wcf.get_msg(block=False)
                if msg is not None:
                    self._msg_queue.put(msg)
            except Empty:
                pass
            except Exception:
                pass
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_text(self, wxid: str, text: str) -> bool:
        """Send a text message. Returns True on success."""
        if not self._wcf:
            return False
        try:
            ret = self._wcf.send_text(text, wxid)
            return ret == 0
        except Exception:
            return False

    def get_contacts(self) -> list[dict]:
        """Return cached contact list."""
        if self._contacts:
            return self._contacts
        if self._wcf:
            self._contacts = self._wcf.get_contacts()
        return self._contacts

    def get_self_info(self) -> dict:
        if self._wcf:
            return self._wcf.get_user_info()
        return {}

    def is_logged_in(self) -> bool:
        return bool(self._my_wxid)

    def poll_messages(self) -> list[dict]:
        """Drain the message queue, return normalized dicts for new messages."""
        msgs: list[dict] = []
        while True:
            try:
                msg = self._msg_queue.get_nowait()
            except Empty:
                break
            normalized = self._normalize(msg)
            if normalized:
                msgs.append(normalized)
        return msgs

    def health_check(self) -> dict:
        return {
            "wcf_alive": self._started and self._wcf is not None,
            "wechat_logged_in": self.is_logged_in(),
            "contacts_count": len(self._contacts),
            "my_wxid": self._my_wxid,
            "target_wxid": self.cfg.target_wxid,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize(self, msg) -> dict | None:
        """Convert WxMsg to a normalized dict for our pipeline.

        Returns None if message should be filtered out.
        """
        try:
            msg_type = msg.type
        except AttributeError:
            return None

        if msg_type != 1:  # text only
            return None

        try:
            sender = msg.sender or ""
            content = msg.content or ""
            ts = msg.ts or 0
            msg_id = msg.id or ""
            is_self = bool(getattr(msg, "_is_self", 0))
            roomid = msg.roomid or ""
        except AttributeError:
            return None

        # Filter by target if configured
        if self.cfg.target_wxid and sender != self.cfg.target_wxid:
            return None

        # Skip self-messages that we sent
        if is_self:
            return None

        return {
            "id": msg_id,
            "type": msg_type,
            "sender": sender,
            "roomid": roomid,
            "ts": ts,
            "content": content,
            "is_self": False,
        }
