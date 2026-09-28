import os
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _chat_ids(raw: str) -> FrozenSet[int]:
    if not raw.strip():
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_IDS must contain comma-separated integers") from exc


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_path: Path
    poll_interval_seconds: float
    default_min_liquidity_usd: float
    default_cooldown_seconds: int
    allowed_chat_ids: FrozenSet[int]
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        return cls(
            telegram_bot_token=token,
            database_path=Path(os.getenv("DATABASE_PATH", "data/zvonki.sqlite3")),
            poll_interval_seconds=_positive_float("POLL_INTERVAL_SECONDS", 2.0),
            default_min_liquidity_usd=max(
                0.0, float(os.getenv("DEFAULT_MIN_LIQUIDITY_USD", "5000"))
            ),
            default_cooldown_seconds=int(os.getenv("DEFAULT_COOLDOWN_SECONDS", "600")),
            allowed_chat_ids=_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

