import asyncio
import logging
import time
import urllib.parse
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .http import JsonHttpClient
from .models import PairSnapshot, Watch


logger = logging.getLogger(__name__)
API_BASE = "https://api.dexscreener.com"


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _same_address(left: str, right: str) -> bool:
    if left.startswith("0x") and right.startswith("0x"):
        return left.lower() == right.lower()
    return left == right


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def select_pair(
    pairs: List[Dict[str, Any]], token_address: str, pinned_pair: str = ""
) -> Optional[PairSnapshot]:
    candidates = []
    for pair in pairs:
        base = pair.get("baseToken") or {}
        if not _same_address(str(base.get("address", "")), token_address):
            continue
        if not pair.get("priceUsd"):
            continue
        if pinned_pair and not _same_address(str(pair.get("pairAddress", "")), pinned_pair):
            continue
        candidates.append(pair)

    if not candidates:
        return None
    chosen = max(candidates, key=lambda item: _number((item.get("liquidity") or {}).get("usd")))
    base = chosen.get("baseToken") or {}
    quote = chosen.get("quoteToken") or {}
    txns_m5 = (chosen.get("txns") or {}).get("m5") or {}
    volume = chosen.get("volume") or {}
    liquidity = chosen.get("liquidity") or {}
    created_at = chosen.get("pairCreatedAt")

    return PairSnapshot(
        chain_id=str(chosen.get("chainId", "")),
        token_address=str(base.get("address", token_address)),
        pair_address=str(chosen.get("pairAddress", "")),
        dex_id=str(chosen.get("dexId", "unknown")),
        symbol=str(base.get("symbol", "?")),
        quote_symbol=str(quote.get("symbol", "?")),
        price_usd=_number(chosen.get("priceUsd")),
        liquidity_usd=_number(liquidity.get("usd")),
        market_cap=_number(chosen.get("marketCap")) if chosen.get("marketCap") is not None else None,
        fdv=_number(chosen.get("fdv")) if chosen.get("fdv") is not None else None,
        volume_m5=_number(volume.get("m5")),
        buys_m5=_integer(txns_m5.get("buys")),
        sells_m5=_integer(txns_m5.get("sells")),
        pair_created_at_ms=_integer(created_at) if created_at is not None else None,
        url=str(chosen.get("url", "")),
    )


class DexScreenerClient:
    def __init__(self, http: JsonHttpClient):
        self.http = http
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def fetch_pairs(self, chain_id: str, token_addresses: Sequence[str]) -> List[Dict[str, Any]]:
        addresses = ",".join(token_addresses)
        path = urllib.parse.quote(addresses, safe=",")
        url = f"{API_BASE}/tokens/v1/{urllib.parse.quote(chain_id, safe='')}/{path}"
        # The documented endpoint limit is 300 requests/minute. Keep a small
        # safety margin and serialize requests from monitoring and bot commands.
        async with self._request_lock:
            wait_for = (60.0 / 285.0) - (time.monotonic() - self._last_request_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            payload = await self.http.request_json(url, timeout=12.0)
            self._last_request_at = time.monotonic()
        if not isinstance(payload, list):
            raise RuntimeError("DexScreener returned an unexpected response")
        return payload

    async def resolve_token(self, chain_id: str, token_address: str) -> Optional[PairSnapshot]:
        pairs = await self.fetch_pairs(chain_id, [token_address])
        return select_pair(pairs, token_address)

    async def snapshots_for(self, watches: Sequence[Watch]) -> Dict[int, PairSnapshot]:
        by_chain: Dict[str, List[Watch]] = defaultdict(list)
        for watch in watches:
            by_chain[watch.chain_id].append(watch)

        output: Dict[int, PairSnapshot] = {}
        for chain_id, chain_watches in by_chain.items():
            unique_addresses = list(dict.fromkeys(w.token_address for w in chain_watches))
            pair_rows: List[Dict[str, Any]] = []
            for address_chunk in _chunks(unique_addresses, 30):
                pair_rows.extend(await self.fetch_pairs(chain_id, address_chunk))

            for watch in chain_watches:
                snapshot = select_pair(pair_rows, watch.token_address, watch.pair_address)
                if snapshot:
                    output[watch.id] = snapshot
        return output
