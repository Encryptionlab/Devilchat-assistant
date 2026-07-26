"""Async LLM service — wraps run.py's synchronous LLM caller with thread-pool bridge."""

import asyncio
import json
import time
from functools import partial
from typing import AsyncGenerator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.config import BASE_URL, MODEL, load_api_key


class LlmService:
    """Async LLM caller. Uses requests in a thread pool for sync calls,
    and httpx/requests streaming for token-by-token output."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or load_api_key()
        self._session: requests.Session | None = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            retry = Retry(
                total=3,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST"],
            )
            self._session = requests.Session()
            self._session.mount("https://", HTTPAdapter(max_retries=retry))
        return self._session

    def _chat_sync(self, system_prompt: str, user_prompt: str, retries: int = 5) -> str:
        """Synchronous LLM call with retry — same logic as run.py's llm_chat."""
        last_error = None
        for attempt in range(retries):
            try:
                resp = self._get_session().post(
                    BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "max_tokens": 4096,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                if resp.status_code == 400:
                    last_error = RuntimeError(f"API 返回 400: {resp.text[:300]}")
                elif resp.status_code == 401:
                    raise RuntimeError(f"API Key 无效: {resp.text[:200]}")
                else:
                    last_error = RuntimeError(f"API 返回 {resp.status_code}: {resp.text[:300]}")
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError) as e:
                last_error = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
        raise RuntimeError(f"API 调用失败（已重试 {retries} 次）: {last_error}")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Async wrapper: run sync _chat_sync in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._chat_sync, system_prompt, user_prompt)
        )

    async def chat_stream(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        """Stream tokens from the LLM API via SSE.

        Runs the sync streaming HTTP call in a thread pool, pushing chunks
        through an asyncio.Queue back to the async world.
        """
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _stream():
            try:
                resp = self._get_session().post(
                    BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "max_tokens": 4096,
                        "stream": True,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                    timeout=120,
                    stream=True,
                )
                if resp.status_code != 200:
                    queue.put(None)
                    return
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = (
                                data.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                queue.put(delta)
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass
            finally:
                queue.put(None)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _stream)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    def as_callable(self):
        """Return a (system, user) -> str callable for use with src/ modules.
        Runs synchronously via requests — safe to call from async context
        since the pipeline runs LLM calls in thread pool anyway."""
        return self._chat_sync
