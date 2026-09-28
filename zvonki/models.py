from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Watch:
    id: int
    chat_id: int
    chain_id: str
    token_address: str
    pair_address: str
    symbol: str
    quote_symbol: str
    dex_id: str
    threshold_percent: float
    window_seconds: int
    min_liquidity_usd: float
    cooldown_seconds: int
    enabled: bool = True


@dataclass(frozen=True)
class PairSnapshot:
    chain_id: str
    token_address: str
    pair_address: str
    dex_id: str
    symbol: str
    quote_symbol: str
    price_usd: float
    liquidity_usd: float
    market_cap: Optional[float]
    fdv: Optional[float]
    volume_m5: float
    buys_m5: int
    sells_m5: int
    pair_created_at_ms: Optional[int]
    url: str


@dataclass(frozen=True)
class Alert:
    watch: Watch
    snapshot: PairSnapshot
    reference_price: float
    change_percent: float
    direction: str
    observed_seconds: float

