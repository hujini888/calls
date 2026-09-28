import logging
from typing import Any, Dict, List

from .http import JsonHttpClient


logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, token: str, http: JsonHttpClient):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.http = http

    async def get_me(self) -> Dict[str, Any]:
        payload = await self.http.request_json(
            f"{self.base_url}/getMe", timeout=15, retries=1
        )
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram getMe failed: {payload}")
        return payload.get("result") or {}

    async def get_updates(self, offset: int, timeout: int = 25) -> List[Dict[str, Any]]:
        payload = await self.http.request_json(
            f"{self.base_url}/getUpdates",
            data={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
            timeout=timeout + 10,
            retries=1,
        )
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {payload}")
        return payload.get("result", [])

    async def send_message(self, chat_id: int, text: str) -> None:
        payload = await self.http.request_json(
            f"{self.base_url}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
            timeout=15,
            retries=2,
        )
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {payload}")
