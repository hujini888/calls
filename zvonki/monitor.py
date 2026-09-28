import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from .database import Database
from .models import Alert, PairSnapshot, Watch


logger = logging.getLogger(__name__)


@dataclass
class _RuleState:
    up_armed: bool = True
    down_armed: bool = True
    last_up_at: Optional[float] = None
    last_down_at: Optional[float] = None


class PriceTracker:
    def __init__(self):
        self.samples: Dict[int, Deque[Tuple[float, float]]] = defaultdict(deque)
        self.states: Dict[int, _RuleState] = {}

    def clear(self, watch_id: int) -> None:
        self.samples.pop(watch_id, None)
        self.states.pop(watch_id, None)

    def evaluate(
        self,
        watch: Watch,
        snapshot: PairSnapshot,
        now: float,
        persisted_last_up: Optional[float] = None,
        persisted_last_down: Optional[float] = None,
    ) -> Optional[Alert]:
        samples = self.samples[watch.id]
        samples.append((now, snapshot.price_usd))
        keep_for = max(watch.window_seconds * 2.0, watch.window_seconds + 60.0)
        while samples and samples[0][0] < now - keep_for:
            samples.popleft()

        target = now - watch.window_seconds
        reference = None
        for sample in reversed(samples):
            if sample[0] <= target:
                reference = sample
                break
        if reference is None or reference[1] <= 0 or snapshot.price_usd <= 0:
            return None

        observed = now - reference[0]
        change = (snapshot.price_usd / reference[1] - 1.0) * 100.0
        state = self.states.setdefault(
            watch.id,
            _RuleState(last_up_at=persisted_last_up, last_down_at=persisted_last_down),
        )

        reset_level = watch.threshold_percent * 0.5
        if change < reset_level:
            state.up_armed = True
        if change > -reset_level:
            state.down_armed = True

        if snapshot.liquidity_usd < watch.min_liquidity_usd:
            return None

        if change >= watch.threshold_percent and state.up_armed:
            if state.last_up_at is None or now - state.last_up_at >= watch.cooldown_seconds:
                state.up_armed = False
                state.last_up_at = now
                return Alert(watch, snapshot, reference[1], change, "up", observed)

        if change <= -watch.threshold_percent and state.down_armed:
            if state.last_down_at is None or now - state.last_down_at >= watch.cooldown_seconds:
                state.down_armed = False
                state.last_down_at = now
                return Alert(watch, snapshot, reference[1], change, "down", observed)
        return None


class Monitor:
    def __init__(self, database: Database, dex, telegram, interval_seconds: float):
        self.database = database
        self.dex = dex
        self.telegram = telegram
        self.interval_seconds = interval_seconds
        self.tracker = PriceTracker()

    async def tick(self) -> None:
        watches = self.database.list_watches(enabled_only=True)
        if not watches:
            return
        snapshots = await self.dex.snapshots_for(watches)
        now = time.time()
        for watch in watches:
            snapshot = snapshots.get(watch.id)
            if not snapshot:
                logger.warning("No DexScreener snapshot for watch %s", watch.id)
                continue
            last_up, last_down = self.database.get_last_alerts(watch.id)
            alert = self.tracker.evaluate(watch, snapshot, now, last_up, last_down)
            if alert:
                try:
                    await self.telegram.send_message(watch.chat_id, format_alert(alert))
                except Exception:
                    logger.exception("Failed to send alert for watch %s", watch.id)
                    continue
                self.database.set_last_alert(watch.id, alert.direction, now)

    async def run(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except Exception:
                logger.exception("Monitoring tick failed")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.1, self.interval_seconds - elapsed))


def _money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"


def _price(value: float) -> str:
    if value >= 1:
        return f"${value:,.6f}"
    return f"${value:.12f}".rstrip("0")


def format_alert(alert: Alert) -> str:
    icon = "🚀" if alert.direction == "up" else "🔻"
    verb = "вырос" if alert.direction == "up" else "упал"
    snap = alert.snapshot
    cap = snap.market_cap if snap.market_cap is not None else snap.fdv
    return (
        f"🔔 ЗВОНОК {icon}\n\n"
        f"{snap.symbol}/{snap.quote_symbol} {verb} на {abs(alert.change_percent):.2f}% "
        f"за {alert.observed_seconds:.0f} сек.\n"
        f"Цена: {_price(alert.reference_price)} → {_price(snap.price_usd)}\n"
        f"Капа/FDV: {_money(cap)}\n"
        f"Ликвидность: {_money(snap.liquidity_usd)}\n"
        f"Объём 5m: {_money(snap.volume_m5)}\n"
        f"Сделки 5m: {snap.buys_m5} покупок / {snap.sells_m5} продаж\n"
        f"Сеть: {snap.chain_id} · DEX: {snap.dex_id}\n\n"
        f"{snap.url}"
    )
