import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class HttpError(RuntimeError):
    pass


class JsonHttpClient:
    def __init__(self, user_agent: str = "zvonki/0.1"):
        self.user_agent = user_agent

    def _request_sync(
        self,
        url: str,
        data: Optional[Dict[str, Any]],
        timeout: float,
        retries: int,
    ) -> Any:
        encoded = None
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if data is not None:
            encoded = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        for attempt in range(retries + 1):
            request = urllib.request.Request(url, data=encoded, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code == 429 or exc.code >= 500:
                    if attempt < retries:
                        retry_after = exc.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                        time.sleep(min(delay, 5.0))
                        continue
                raise HttpError(f"HTTP {exc.code} from {url}: {body}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise HttpError(f"Request failed for {url}: {exc}") from exc

        raise HttpError(f"Request failed for {url}")

    async def request_json(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._request_sync, url, data, timeout, retries
        )

